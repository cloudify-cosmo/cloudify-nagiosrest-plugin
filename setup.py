from setuptools import setup

setup(
    name='cloudify-nagiosrest-plugin',
    version='0.6.1',
    packages=[
        'nagiosrest_plugin',
    ],
    install_requires=['cloudify-plugins-common>=3.3.1',
                      'requests>=2.18.4,<3.0.0'],
)
