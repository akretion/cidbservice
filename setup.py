from setuptools import find_packages, setup

setup(
    name="cidbservice",
    version="0.1",
    url="https://www.akretion.com",
    author="Sylvain Calador",
    author_email="sylvain.calador@akretion.com",
    description="Mini webservice for databases provisioning",
    packages=find_packages(),
    license="AGPL",
    install_requires=[
        r.strip() for r in open("requirements.txt").read().splitlines()
    ],
)
