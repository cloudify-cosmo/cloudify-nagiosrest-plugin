from setuptools import setup

setup(
    name='cloudify-nagiosrest-plugin',
    version='1.1.1',
    packages=[
        'nagiosrest_plugin',
    ],
    install_requires=['cloudify-common>=4.4.0',
                      'requests>=2.18.4,<3.0.0'],
)
