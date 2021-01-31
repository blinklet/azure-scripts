from setuptools import setup

setup(
    name='AzRuntime',
    url='https://github.com/blinklet/azure-scripts/azruntime',
    author='Brian Linkletter',
    author_email='mail@brianlinkletter.ca',
    packages=['azruntime'],
    install_requires=[
        'azure-identity',
        'azure-mgmt-resource',
        'azure-mgmt-compute',
        'azure-mgmt-monitor',
        'azure-cli-core',
        'tabulate'
    ],
    version='0.3',
    license='GPLv3',
    description='Print a list of all running VMs in your subscriptions. Use must be logged into Azure CLI.',
    long_description=open('README.md').read(),
)