"""setup.py."""
from setuptools import setup, find_packages

with open('requirements.in', 'r') as req_file:
    install_requires = req_file.readlines()

with open('README.rst', 'r', encoding='utf-8') as fh:
    long_description = fh.read()

setup(
    name='sailor',
    version='0.0.1',
    author='DSC Data Science Team',
    author_email='project.sailor@sap.com',
    url='https://github.com/SAP/project-sailor',
    description=('Easily access data from your SAP Digital Supply Chain products for datascience projects like '
                 'predictive maintenance, master data analysis or anything else.'),
    long_description=long_description,
    long_description_content_type='text/x-rst',
    keywords='',
    license='',
    packages=find_packages(include=('sailor', 'sailor.*')),
    python_requires='~=3.8',
    install_requires=install_requires,
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3.8',
    ],
    project_urls={  # Optional
        'Documentation': 'https://sap.github.io/project-sailor',
        'Blog': 'https://blogs.sap.com/',
    },
)