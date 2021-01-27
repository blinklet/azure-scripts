from azure.common.credentials import get_azure_cli_credentials
from azure.mgmt.resource import SubscriptionClient, ResourceManagementClient
credentials, subscription_id, tenant_id = get_azure_cli_credentials(with_tenant=True)
print(credentials)
print(subscription_id)
print(tenant_id)
subscription_client = SubscriptionClient(credentials)
subscriptions = subscription_client.subscriptions.list()
for subscription in subscriptions:
    print(subscription.subscription_id)