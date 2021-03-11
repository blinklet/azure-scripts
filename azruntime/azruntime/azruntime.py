"""
List all VMs in your subscriptions in a formatted table.
The columns are: VM name, subscription, resource group, size, 
location, and status. Each row represents a unique VM.

When you run it, the script will launch a browser window which 
will start the Azure interactive login process. So, this script 
must be run on a desktop environment.

Prerequisites:
(env) $ pip install azure-mgmt-resource azure-mgmt-compute \
        azure-identity rich azure-mgmt-monitor
"""
from azure.mgmt.resource import SubscriptionClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.identity import DefaultAzureCredential
from datetime import datetime, timezone, timedelta
from operator import itemgetter
from rich.console import Console
from rich.table import Table
import time

def sublist(client):
    return [(sub.subscription_id, sub.display_name) for sub in client.subscriptions.list()] 


def vmlist(client):
    return [(vm.name, vm.id) for vm in client.virtual_machines.list_all()]


def vmsize(client, group, vm):
    return client.virtual_machines.get(group, vm).hardware_profile.vm_size


def vmlocation(client, group, vm):
    return client.virtual_machines.get(group, vm).location


def vmstatus(client, group, vm):
    ''' 
    Returns the power state of a VM instance. If there is no state to 
    read, returns state = "Unknown".
    '''

    # Sometimes, the instanceview.statuses list is empty or contains only one element.
    # This occurs when a VM fails to deploy properly but also it seems to
    # occasionally occur for no obvious reason. We check for it and move on.
    try:
        results = client.virtual_machines.instance_view(group, vm).statuses[1].code
    except IndexError:
        return 'Unknown'

    # Status code is always a two-part code, divided by a forward-slash.
    # The first is usually "PowerState" and the second is "running" or "deallocated".
    powerstate, status = results.split('/')  
    return status


def diff_time(start_time, vm_status):
    """Calculates the time difference between the VM's log timestamp and the present time.

    The color used in the returned style tag will differ if the vmstatus is
    'running' or 'deallocated'. We use different styles to running highlight 
    VMs that have been running too long, or deallocated VMs that are too old.

    Args:
        start_time (str): A timestamp string in datetime format
        vm_status (str): Must be either 'running' or 'deallocated'

    Raises:
        ValueError: If invalid vm_status is passed to this function

    Returns:
        tuple:
            uptime_string (str): Example - '2 days, 12 hours' 
            style_tag (str): Example - 'dark_sea_green4 dim'
    """

    now = datetime.now(timezone.utc)
    uptime = (now - start_time) / timedelta(hours=1)
    uptime_string = ""
    style_tag = ""
    
    uptime_days = int(uptime) // 24
    uptime_hours = int(uptime) % 24

    # build uptime string to return
    if uptime_days == 0:
        uptime_string = str(uptime_hours) + ' hours'
    else:
        uptime_string = str(uptime_days) + ' days, '+ str(uptime_hours) + ' hours'

    # set color for row style tag to return
    if vm_status == "running":
        if uptime_days == 0:
            style_tag = "dark_sea_green4"
        elif uptime_days == 1:
            style_tag = "gold1"
        elif uptime_days == 2:
            style_tag = "dark_orange"
        elif uptime_days >= 3:
             style_tag = "orange_red1"
    elif vm_status == "deallocated":
        if uptime_days < 14:
            style_tag = "dark_sea_green4 dim"
        elif uptime_days >= 14 and uptime_days <= 28:
            style_tag = "gold1 dim"
        elif uptime_days > 28:
            style_tag = "dark_orange dim"
    else:
        raise ValueError("vm_status is not expected value")

    return uptime_string, style_tag


def get_vm_time(vm_id, monitor_client, vm_status='running'):
    """Looks for the VM's most recent startup or shutdown log within the past 89 days. 

    Args:
        vm_id (str): Virtual machine ID
        monitor_client (azure.mgmt.monitor._monitor_management_client.MonitorManagementClient()): Microsoft Azure activity monitor API client
        vm_status (str, optional): Should be either 'running' or 'deallocated'. Defaults to 'running'.

    Returns:
        tuple: 
            uptime_string (str): Example - '2 days, 12 hours' 
            style_tags (str): Example - 'dark_sea_green4 dim'
    """

    # If you filter using a date older than 89 days, you may see 
    # an error message like: "msrest.exceptions.DeserializationError"
    past_date = datetime.now(timezone.utc) - timedelta(days=89)

    filter = " and ".join([
        f"eventTimestamp ge '{past_date.date()}T00:00:00Z'",
        f"resourceUri eq '{vm_id}'"
    ])
    
    select = ','.join([
        'operationName',
        'eventTimestamp',
        'status'
    ])

    logs = monitor_client.activity_logs.list(filter=filter, select=select)

    #######################################################
    # The following code block is commented out because I replaced it with the 
    # code further below, which is easier to read. But I did not want to lose this example
    # of using the next() function to get the first occurance of a condition in
    # an iterable. See: https://stackoverflow.com/questions/9542738/python-find-in-list
    ###########################################################
    # if vm_status == 'deallocated':
    #     return(next((diff_time(log.event_timestamp, vm_status) for log in logs if (log.operation_name.value == 'Microsoft.Compute/virtualMachines/deallocate/action') and (log.status.value == 'Succeeded')), ('>90 days', "red3 dim")))
    #
    # if vm_status == 'running':
    #     return(next((diff_time(log.event_timestamp, vm_status) for log in logs if (((log.operation_name.value == 'Microsoft.Compute/virtualMachines/start/action') or (log.operation_name.value == 'Microsoft.Compute/virtualMachines/write')) and (log.status.value == 'Succeeded'))), ('>90 days', "red3 bold")))
    ###########################################################

    # If the for loop in either of the if blocks below completes 
    # without finding a successful VM start or create log,
    # or if the logs iterator is empty (so loop does not execute), 
    # then the VM has been running for more than 90 days.
    if vm_status == 'running':
        for log in logs:
            vm_started = (log.operation_name.value == 'Microsoft.Compute/virtualMachines/start/action')
            vm_created = (log.operation_name.value == 'Microsoft.Compute/virtualMachines/write')
            succeeded = (log.status.value == 'Succeeded')
            if (vm_started or vm_created) and succeeded:
                uptime_string, style_tags = diff_time(log.event_timestamp, vm_status)
                return uptime_string, style_tags
        return '>90 days', "red3 bold"

    if vm_status == 'deallocated':
        for log in logs:
            vm_deallocated = (log.operation_name.value == 'Microsoft.Compute/virtualMachines/deallocate/action')
            succeeded = (log.status.value == 'Succeeded')
            if vm_deallocated and succeeded:
                uptime_string, style_tags = diff_time(log.event_timestamp, vm_status)
                return uptime_string, style_tags
        return '>90 days', "red3 dim"


def build_vm_list(credentials, status):
    """Build a list of all VMs in all the subscriptions visible to the user.

    Args:
        credentials (azure.core.credentials.AzureKeyCredential()): Microsoft Azure credential token
        status (rich.status.Status): A context manager for the console status updates.

    Returns:
        list: The returned list contains nested lists, one header list, and one list
              for each VM. Each nested list contains the VM name, subscription, 
              resource group, size, location, status, uptime, and style.
              The style column is used to format the table that will be built using
              this list as an argument.
    """
    headers = [
        'VM name',
        'Subscription',
        'ResourceGroup',
        'Size',
        'Location',
        'Status',
        'TimeInState',
        'style'
    ]

    returned_list = list()
    returned_list.append(headers)

    status.update("[green4]Getting subscriptions[/green4]")

    with SubscriptionClient(credentials) as subscription_client:
        subscriptions = sublist(subscription_client)

        for subscription_id, subscription_name in subscriptions:

            with ComputeManagementClient(credentials, subscription_id) as compute_client, MonitorManagementClient(credentials, subscription_id) as monitor_client:

                vms = vmlist(compute_client)

                for vm_name, vm_id in vms:

                    resource_group = vm_id.split('/')[4].lower()

                    status.update(
                        "[grey74]Subscription: [green4]" +
                        subscription_name +
                        "[/green4]  Resource Group: [green4]" +
                        resource_group +
                        "[/green4]  VM: [green4]" +
                        vm_name +
                        "[/green4][/grey74]"
                    )

                    vm_status = vmstatus(compute_client, resource_group, vm_name)
                    vm_size = vmsize(compute_client, resource_group, vm_name)
                    vm_location = vmlocation(compute_client, resource_group, vm_name)

                    if vm_status == 'running':
                        vm_time, style_tag = get_vm_time(vm_id, monitor_client, vm_status="running")
                    elif vm_status == "deallocated":
                        vm_time, style_tag = get_vm_time(vm_id, monitor_client, vm_status="deallocated")
                    elif vm_status == 'Unknown':
                        vm_time, style_tag = 'Unknown', 'sky_blue3'
                    else:
                        vm_time, style_tag = '???', 'sky_blue3'  # if unexpected result

                    returned_list.append([
                        vm_name, 
                        subscription_name, 
                        resource_group, 
                        vm_size, 
                        vm_location, 
                        vm_status, 
                        vm_time, 
                        style_tag
                    ])

    return returned_list


def sort_by_column(input_list, *sort_keys):
    """Sort a list by columns, except for the first row"""
    
    headers = input_list[0]
    list_to_sort = input_list[1:]
    x = [headers.index(column) for column in sort_keys]

    list_to_sort.sort(key=itemgetter(*x))
    list_to_sort.insert(0, headers)
    return list_to_sort


def vm_table(status):
    """Build a table showing the length of time each VM in your subscriptions
    is in either 'running' or 'deallocated' status. 
    
    An example of the way to call this function is shown below:

        console = Console()
        with console.status("[green4]Starting[/green4]") as status:
            console.print(vm_table(status))

    Args:
        status (rich.status.Status): A context manager for the console status updates.
        Use the same Console() instance that you will use to print the table object.

    Returns:
        rich.table.Table: A Rich-formatted table object
    """
    status.update("[green4]Getting your Azure credentials[/green4]")

    credentials = DefaultAzureCredential(
        exclude_environment_credential = True,
        exclude_managed_identity_credential = True,
        exclude_shared_token_cache_credential = True,
        exclude_visual_studio_code_credential = True,
        exclude_interactive_browser_credential = False
    )
    vm_list = build_vm_list(credentials, status)

    if len(vm_list) > 1:  # An empty vm_list still has a header row
        sorted_list = sort_by_column(vm_list,'Status','ResourceGroup','Size')

        table = Table(show_header=True, header_style="bold", show_lines=True)

        # The column headers are in the first row of the list.
        # Remove the style column from the header row.
        header_list = sorted_list[0][:-1] 

        # Set up the table columns using the list of headers
        for column_name in header_list: 
            table.add_column(column_name)

        # Each row is a nested list.
        # Unpack each nested list into arguments for the add_row function
        # Remove the style column from the end of each row and
        # save its value and use it to format the row in the table.
        for row in sorted_list[1:]:
            style_tag = row.pop()
            table.add_row(*row, style=style_tag)

        return table
    else:
        return "No VMs found"


def main():
    """Set up a Rich console context and call the vm_table() function
    that returns the Rich table object. Print the table using Rich.
    """
    with Console() as console:
        with console.status("[green4]Starting[/green4]") as status:
            console.print(vm_table(status))



if __name__ == '__main__':
    start_time = time.perf_counter()
    main()
    elapsed = time.perf_counter() - start_time
    print(f"Operation completed in {elapsed:0.2f} seconds.")
    
