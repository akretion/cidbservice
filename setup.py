from setuptools import setup, find_packages

setup(
    name = 'cidbservice',
    version = '0.1',
    url = 'https://www.akretion.com',
    author = 'Sylvain Calador',
    author_email = 'sylvain.calador@akretion.com',
    description = 'Mini webservice for databases provisioning',
    packages = find_packages(),
    license = 'AGPL',
    install_requires = [
	'Flask',
	'psycopg2',
	'configparser',
    ]
)
