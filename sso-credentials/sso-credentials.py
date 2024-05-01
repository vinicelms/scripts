#!/usr/bin/python3

import boto3
import urllib3
import re
import os
import time
import socket
import json
import webbrowser
import inquirer
import logging
import argparse
import unidecode
from configobj import ConfigObj
from bs4 import BeautifulSoup

logger = logging.getLogger()
logger.setLevel("INFO")
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] | %(message)s"))
logger.addHandler(handler)


def get_hostname():
    hostname = socket.gethostname()
    logger.info(f"Hostname returned: {hostname}")
    return hostname


def get_region_sso(sso_url):
    logger.info("Searching SSO region")
    regex_region = r"^\s{1,}.*(content\=\"(?P<region>.*)\").*$"
    http = urllib3.PoolManager()
    logger.info(f"Opening connection page: {sso_url}")
    req = http.request("GET", sso_url)
    if req.status == 200:
        logger.info("Página was returned with success")
    else:
        logger.error(req.data)
    req = req.data.decode("utf-8")
    soup = BeautifulSoup(req, "html.parser")
    region = soup.find(id="env").get_text()
    region = json.loads(region)["region"]
    return region


def get_token(client_name, region, sso_url):
    logger.info("Starting process to get token")
    client = boto3.client("sso-oidc", region_name=region)
    logger.info("Registering client")
    register = client.register_client(clientName=client_name, clientType="public")
    logger.info("Starting device authorization")
    authz = client.start_device_authorization(
        clientId=register.get("clientId"),
        clientSecret=register.get("clientSecret"),
        startUrl=sso_url,
    )
    logger.info("Opening browser to authorize session")
    logger.info(
        f"If you're using WSL, your browser doesn't will open. To solve that, access this link: {authz.get('verificationUriComplete')}"
    )
    webbrowser.open(authz.get("verificationUriComplete"))

    flag_verify = True
    wait_time = 300
    token_response = None
    while flag_verify:
        try:
            token_response = client.create_token(
                clientId=register.get("clientId"),
                clientSecret=register.get("clientSecret"),
                grantType="urn:ietf:params:oauth:grant-type:device_code",
                deviceCode=authz.get("deviceCode"),
            )
        except Exception:
            pass
        time.sleep(1)
        wait_time = wait_time - 1
        if wait_time == 0 or token_response:
            flag_verify = False
    if token_response:
        logger.debug("Token was generated with success")
        return token_response.get("accessToken")
    else:
        logger.error("Was not possible to generate token")
        return None


def configure_credentials_file(account_list, sso_url, region):
    file_location = os.path.join(
        os.path.expanduser("~"), f".aws{os.path.sep}credentials"
    )
    logger.info(f"Writing credentials file: {file_location}")
    config = ConfigObj(file_location)
    for account in account_list:
        logger.info(f"Writing account informations: {account.name}")
        config[account.name] = {}
        config[account.name]["sso_start_url"] = sso_url
        config[account.name]["sso_region"] = region
        config[account.name]["sso_account_id"] = account.id
        if len(account.roles) > 1:
            questions = [
                inquirer.List(
                    "role",
                    message=f"Choose desired Role to this account: {account.name}",
                    choices=account.roles,
                )
            ]
            answer = inquirer.prompt(questions)
            config[account.name]["sso_role_name"] = answer["role"]
        else:
            config[account.name]["sso_role_name"] = account.roles[0]
        # config.comments[account.name].insert(0, "") # Add blank line
        config.write()

    file_location = os.path.join(os.path.expanduser("~"), f".aws{os.path.sep}config")
    logger.info(f"Writing config file: {file_location}")
    config = ConfigObj(file_location)
    for account in account_list:
        logger.info(f"Writing account informations: {account.name}")
        config[account.name] = {}
        config[account.name]["region"] = "us-east-1"
        config[account.name]["format"] = "json"
        config[account.name]["output"] = "json"
        # config.comments[account.name].insert(0, "") # Add blank line
        config.write()


class AWSIntegration:
    def __init__(self, region, access_token):
        self.__client = boto3.client("sso", region_name=region)
        self.access_token = access_token

    def get_account_list(self, prefix, spelling, separator):
        logger.info("Obtaining accounts list")
        accounts_info = {"account_list": [], "next_token": None}
        run = True
        while run:
            if accounts_info["next_token"]:
                accs = self.__client.list_accounts(
                    accessToken=self.access_token, nextToken=accounts_info["next_token"]
                )
            else:
                accs = self.__client.list_accounts(accessToken=self.access_token)
            accounts_info["account_list"].extend(accs["accountList"])
            if "nextToken" in accs:
                accounts_info["next_token"] = accs["nextToken"]
                logger.info("Looking for more accounts...")
            else:
                run = False
                logger.info("Account search process finished")
        logger.info(f"Accounts found: {len(accounts_info['account_list'])}")
        accounts = []
        for account in accounts_info["account_list"]:
            logger.info(f"Listing account roles: {account['accountName']}")
            acc = Account(
                id=account["accountId"],
                name=account["accountName"],
                prefix=prefix,
                spelling=spelling,
                separator=separator,
            )
            role_list = self.__client.list_account_roles(
                accessToken=self.access_token, accountId=acc.id
            )
            for role in role_list["roleList"]:
                acc.roles.append(role["roleName"])
            logger.info(
                f"Were found {len(acc.roles)} on the account {account['accountName']}"
            )
            accounts.append(acc)

        return accounts


class Account:
    def __init__(self, id, name, prefix, spelling, separator):
        self.id = id
        self.name = self.normalize_name(name, prefix, spelling, separator)
        self.roles = []

    def normalize_name(self, name, prefix, spelling, separator):
        name = name.lower() if spelling == "lower" else name.upper()
        name = f"{prefix}{separator}{name}" if prefix else name
        name = unidecode.unidecode(name)
        name = name.replace("-", separator)
        name = name.replace("_", separator)
        name = name.replace(" ", separator)
        while f"{separator}{separator}" in name:
            name = name.replace(f"{separator}{separator}", separator)
        return name


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Important informations:\n"
        "- This script will connect through the SSO URL informed\n"
        "- No credentials are stored\n"
        "- The authentication methods followed, are those suggested by AWS\n"
        "- Existing accounts will not be removed, but accounts with the same name will be overwritten\n"
        "- If any account no longer exists in the organization, it will not be removed from the file\n"
        "- The AWS accounts, together with the policies defined, will only be listed, without any change\n\n"
        "Standard rules for defining account names (can be changed, see parameters):\n"
        '- All characters will be tiny (see the option "spelling")\n'
        '- Accents will be removed.If there is: "conexão" (PT-BR), it will be changed to "conexao" (non-alterable rule)\n'
        '- Spaces will be replaced by trace/hyphen (see option "separator")',
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Enter SSO's address.Example: https://example.awsapps.com/start",
    )
    parser.add_argument(
        "--prefix",
        required=False,
        help='If you wish, enter a prefix for the accounts. (default: "%(default)s")'
        "This option is interesting when there is more than one organization involved\n"
        "\tExample:\n"
        '\t - Account name: "my-account"\n'
        '\t - Prefix: "new"\n'
        '\t - Separator: "-"\n'
        "\t - Account final name: new-my-account",
    )
    parser.add_argument(
        "--spelling",
        required=False,
        choices=["upper", "lower"],
        default="lower",
        help='Enter if you want the names of the accounts like: uppercase or lowercase (default: "%(default)s")',
    )
    parser.add_argument(
        "--separator",
        required=False,
        default="-",
        help='Enter the accounts separator (default: "%(default)s")',
    )
    args = parser.parse_args()

    logger.info("Starting execution ...")
    client_name = get_hostname()
    url = args.url
    region = get_region_sso(url)
    if not region:
        exit(1)
    token = get_token(client_name, region, url)
    aws = AWSIntegration(region=region, access_token=token)
    accounts = aws.get_account_list(
        spelling=args.spelling, separator=args.separator, prefix=args.prefix
    )
    configure_credentials_file(accounts, url, region)
