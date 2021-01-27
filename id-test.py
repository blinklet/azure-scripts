"""
list-running-vms.py: 

To install dependencies:
sudo apt update
pip install wheel 
pip install azure-identity azure-cli-core msrestazure
pip install azure-mgmt-resource 
"""

from azure.identity import AzureCliCredential
from azure.mgmt.resource import SubscriptionClient, ResourceManagementClient


if __name__ == '__main__':
    credentials = AzureCliCredential()
    print(credentials)
    # print(subscription_id)
    # print(tenant_id)
    subscription_client = SubscriptionClient(credentials)
    subscriptions = subscription_client.subscriptions.list()
    for subscription in subscriptions:
        print(subscription.subscription_id)



