from setuptools import setup

setup(
    name="aws-lambda-ci",
    version="0.0.8",
    url="https://github.com/obytes/aws-lambda-ci",
    license="Apache License 2.0",
    author="Hamza Adami",
    author_email="me@adamihamza.com",
    description="Continuous integration pipeline for aws lambda function",
    keywords="aws,lambda,ci,cd,serverless",
    platforms='any',
    py_modules=["ci"],
    install_requires=[
        "boto3",
        "awslogs"
    ],
    python_requires=">=3.6",
    entry_points={
        'console_scripts': [
            'aws-lambda-ci = ci:ci',
        ],
    },
)
