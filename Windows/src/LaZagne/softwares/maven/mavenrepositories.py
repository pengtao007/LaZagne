import os
from config.write_output import print_output, print_debug
from config.constant import *
from config.header import Header
from config.moduleInfo import ModuleInfo
import xml.etree.ElementTree as ET

class MavenRepositories(ModuleInfo):

    def __init__(self):
        options = {'command': '-t', 'action': 'store_true', 'dest': 'mavenrepositories', 'help': 'Maven repositories'}
        ModuleInfo.__init__(self, 'mavenrepositories', 'maven', options)
        # Interesting XML nodes in Maven repository configuration
        self.nodes_to_extract = ["id", "username", "password", "privateKey", "passphrase"]
        self.settings_namespace = "{http://maven.apache.org/SETTINGS/1.0.0}"

    def extract_master_password(self):
        """
        Detect if a Master password exists and then extract it.

        See https://maven.apache.org/guides/mini/guide-encryption.html#How_to_create_a_master_password

        :return: The master password value or None if no master password exists.
        """
        master_password = None
        master_password_file_location = os.environ.get("USERPROFILE") + "\\.m2\\settings-security.xml"
        if os.path.isfile(master_password_file_location):
            try:
                config = ET.parse(master_password_file_location).getroot()
                master_password_node = config.find(".//master")
                if master_password_node is not None:
                    master_password = master_password_node.text
            except Exception as e:
                print_debug("ERROR", "Cannot retrieve master password '%s'" % e)
                master_password = None

        return master_password


    def extract_repositories_credentials(self):
        """
        Extract all repositories's credentials.

        See https://maven.apache.org/settings.html#Servers

        :return: List of dict in which one dict contains all information for a repository.
        """
        repos_creds = []
        maven_settings_file_location = os.environ.get("USERPROFILE") + "\\.m2\\settings.xml"
        if os.path.isfile(maven_settings_file_location):
            try:
                settings = ET.parse(maven_settings_file_location).getroot()
                server_nodes = settings.findall(".//%sserver" % self.settings_namespace)
                for server_node in server_nodes:
                    creds = {}
                    for child_node in server_node:
                        tag_name = child_node.tag.replace(self.settings_namespace, "")
                        if tag_name in self.nodes_to_extract:
                            creds[tag_name] = child_node.text.strip()
                    if len(creds) > 0:
                        repos_creds.append(creds)
            except Exception as e:
                print_debug("ERROR", "Cannot retrieve repositories credetentials '%s'" % e)
                pass

        return repos_creds

    def use_key_auth(self, creds_dict):
        """
        Utility function to determine if a repository use private key authentication.

        :param creds_dict: Repository credentials dict
        :return: True only if the repositry use private key authentication
        """
        state = False
        if "privateKey" in creds_dict:
            pk_file_location = creds_dict["privateKey"]
            pk_file_location = pk_file_location.replace("${user.home}", os.environ.get("USERPROFILE"))
            state = os.path.isfile(pk_file_location)

        return state


    def run(self):
        """
        Main function:

        - For encrypted password, provides the encrypted version of the password with the master password in order
        to allow "LaZagne run initiator" the use the encryption parameter associated with the version of Maven because
        encryption parameters can change between version of Maven.

        - "LaZagne run initiator" can also use the encrypted password and the master password "AS IS"
        in a Maven distribution to access repositories.

        See https://github.com/jelmerk/maven-settings-decoder
        See https://github.com/sonatype/plexus-cipher/blob/master/src/main/java/org/sonatype/plexus/components/cipher/PBECipher.java
        """
        # Print title
        title = "MavenRepositories"
        Header().title_info(title)

        # Extract the master password
        master_password = self.extract_master_password()

        # Extract all available repositories credentials
        repos_creds = self.extract_repositories_credentials()

        # Parse and process the list of repositories's credentials
        # 3 cases are handled:
        # => Authentication using password protected with the master password (encrypted)
        # => Authentication using password not protected with the master password (plain text)
        # => Authentication using private key
        pwd_found = []
        for creds in repos_creds:
            values = {}
            values["Id"] = creds["id"]
            values["Username"] = creds["username"]
            if not self.use_key_auth(creds):
                pwd = creds["password"].strip()
                # Case for authentication using password protected with the master password
                if pwd.startswith("{") and pwd.endswith("}"):
                    values["SymetricEncryptionKey"] = master_password
                    values["PasswordEncrypted"] = pwd
                else:
                    values["Password"] = pwd
            else:
                # Case for authentication using private key
                pk_file_location = creds["privateKey"]
                pk_file_location = pk_file_location.replace("${user.home}", os.environ.get("USERPROFILE"))
                with open(pk_file_location, "r") as pk_file:
                    values["PrivateKey"] = pk_file.read().replace("\n", "").strip()
                if "passphrase" in creds:
                    values["Passphrase"] = creds["passphrase"]
            pwd_found.append(values)

        # Print the results
        print_output(title, pwd_found)
