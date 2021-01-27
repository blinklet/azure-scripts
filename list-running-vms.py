"""
list-running-vms.py: 

To install dependencies:
sudo apt update
sudo apt install libgirepository1.0-dev gcc libcairo2-dev pkg-config python3-dev gir1.2-gtk-3.0
sudo apt install gir1.2-secret-1
pip install wheel 
pip install pycairo PyGObject
pip install azure-mgmt-resource azure-mgmt-compute azure-mgmt-monitor
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



