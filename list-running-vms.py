"""
list-running-vms.py: 

To install dependencies:
pip install azure-cli
"""

from azure.common.credentials import get_azure_cli_credentials

if __name__ == '__main__':
    credentials = get_azure_cli_credentials()[0]
    print(credentials)

