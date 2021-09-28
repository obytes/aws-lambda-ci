##################
AWS Lambda CI
##################

Continuous integration pipeline for aws lambda function

.. image:: https://github.com/obytes/aws-lambda-ci/raw/main/docs/images/demo_code_changed_deps_changed.gif

*********
Features
*********

✅ Supports the two famous lambda runtimes python and nodejs.

✅ Supports installing custom packages that does not exist in lambda runtime passed to CI process as a
package's descriptor file path in git repository.

✅ Supports installing custom pip/npm dependencies that does not exist in lambda runtime and passed to CI process as a
package's descriptor file path, `packages.json` or `requirements.txt`.

✅ The integration/deployment process is fast thanks to code and dependencies caching.

✅ The lambda dependencies packages are built in a sandboxed local environment that replicates the live AWS Lambda
environment almost identically – including installed software and libraries.

✅ The pipeline does not break the currently published version and traffic shifting between the  current and new 
deployment is seamless.

************
Requirements
************


IAM Permissions
===============

The user/role that call this pipeline should have these permissions attached to it.

.. code-block:: json

    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "",
                "Effect": "Allow",
                "Action": [
                    "s3:ListBucket",
                    "s3:GetObject"
                ],
                "Resource": [
                    "arn:aws:s3:::artifacts-bucket-name/*",
                    "arn:aws:s3:::artifacts-bucket-name"
                ]
            },
            {
                "Sid": "",
                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                    "s3:GetObject"
                ],
                "Resource": [
                    "arn:aws:s3:::artifacts-bucket-name/lambda-ci/function-name/*",
                    "arn:aws:s3:::artifacts-bucket-name/lambda-ci/function-name"
                ]
            },
            {
                "Sid": "",
                "Effect": "Allow",
                "Action": [
                    "lambda:UpdateFunctionConfiguration",
                    "lambda:UpdateFunctionCode",
                    "lambda:UpdateAlias",
                    "lambda:PublishVersion",
                    "lambda:GetFunction"
                ],
                "Resource": "arn:aws:lambda:us-east-1:YOUR_ACCOUNT_ID:function:function-name"
            },
            {
                "Sid": "",
                "Effect": "Allow",
                "Action": [
                    "lambda:PublishLayerVersion",
                    "Lambda:ListLayerVersions"
                ],
                "Resource": "arn:aws:lambda:us-east-1:YOUR_ACCOUNT_ID:layer:function-layer-name"
            },
            {
                "Sid": "",
                "Effect": "Allow",
                "Action": "lambda:GetLayerVersion",
                "Resource": "arn:aws:lambda:us-east-1:YOUR_ACCOUNT_ID:layer:function-layer-name:*"
            }
        ]
    }

Packages
========

- ``python3``
- ``docker``


*****
Usage
*****

Installation
============

.. code-block:: bash

    pip3 install aws-lambda-ci


Arguments
=========

These are the available arguments:

+--------------------------------+--------------------------------------------------------------------------------------------------------------------------------------------+
|              ARG               |                                                                    USAGE                                                                   |
+================================+============================================================================================================================================+
| --app-s3-bucket                | The s3 bucket name that will hold the application code and dependencies                                                                    |
|                                +----------+--------------------------------------+------------------------------------------------------------------------------------------+
|                                | Required | Default: None                        | Allowed: existing S3 bucket name                                                         |
+--------------------------------+----------+--------------------------------------+------------------------------------------------------------------------------------------+
| --function-name                | AWS lambda function name                                                                                                                   |
|                                +----------+--------------------------------------+------------------------------------------------------------------------------------------+
|                                | Required | Default: None                        | Allowed: existing lambda function name                                                   |
+--------------------------------+----------+--------------------------------------+------------------------------------------------------------------------------------------+
| --function-runtime             | AWS lambda function runtime (eg: python3.7)                                                                                                |
|                                +----------+--------------------------------------+------------------------------------------------------------------------------------------+
|                                | Optional | Default: ``python3.8``               | Allowed: ``pythonX.x``|``nodejsX.x``                                                     |
+--------------------------------+----------+--------------------------------------+------------------------------------------------------------------------------------------+
| --function-alias-name          | AWS Lambda alias name (eg: latest)                                                                                                         |
|                                +----------+--------------------------------------+------------------------------------------------------------------------------------------+
|                                | Optional | Default: ``latest``                  | Allowed: version tag (eg: ``latest``, ``qa``, ``prod`` ...)                              |
+--------------------------------+----------+--------------------------------------+------------------------------------------------------------------------------------------+
| --function-layer-name          | AWS Lambda layer name (eg: demo-lambda-dependencies)                                                                                       |
|                                +----------+--------------------------------------+------------------------------------------------------------------------------------------+
|                                | Optional | Default: ``{function-name}-deps``    | Allowed: a valid layer name                                                              |
+--------------------------------+----------+--------------------------------------+------------------------------------------------------------------------------------------+
| --app-src-path                 | Lambda function sources directory that will be archived (eg: demo-lambda/src)                                                              |
|                                +----------+--------------------------------------+------------------------------------------------------------------------------------------+
|                                | Optional | Default: current directory           | Allowed: an existing directory with source code                                          |
+--------------------------------+----------+--------------------------------------+------------------------------------------------------------------------------------------+
|                                | Packages descriptor path (eg: demo-lambda/requirements.txt)                                                                                |
| --app-packages-descriptor-path +----------+--------------------------------------+------------------------------------------------------------------------------------------+
|                                | Optional | Default: ``requirements.txt``        | Allowed: an existing and valid  ``requirements.txt`` or ``package.json``                 |
+--------------------------------+----------+--------------------------------------+------------------------------------------------------------------------------------------+
| --source-version               | The unique revision id (eg: github commit sha, or SemVer tag)                                                                              |
|                                +----------+--------------------------------------+------------------------------------------------------------------------------------------+
|                                | Optional | Default: Random hash                 | Allowed: ``commit`` hash | ``tag`` ver                                                   |
+--------------------------------+----------+--------------------------------------+------------------------------------------------------------------------------------------+
| --aws-profile-name             | AWS profile name (if not provided, will use default aws env variables)                                                                     |
|                                +----------+--------------------------------------+------------------------------------------------------------------------------------------+
|                                | Optional | Default: None                        | Allowed: existing aws profile name                                                       |
+--------------------------------+----------+--------------------------------------+------------------------------------------------------------------------------------------+
| --watch-log-stream             | Watch lambda log stream in realtime after publishing the function                                                                          |
|                                +----------+--------------------------------------+------------------------------------------------------------------------------------------+
|                                | Optional | Default: True                        | Allowed: Boolean                                                                         |
+--------------------------------+----------+--------------------------------------+------------------------------------------------------------------------------------------+


Example
========

.. code-block:: bash

    aws-lambda-ci \
    --app-s3-bucket "kodhive-prd-useast1-ippan-core-artifacts" \
    --function-name "useast1-mimoto-api-v1-codeless" \
    --function-runtime "python3.7" \
    --function-alias-name "latest" \
    --function-layer-name "useast1-mimoto-api-v1-codeless-deps" \
    --app-src-path "app/api/src" \
    --app-packages-descriptor-path "app/api/src/requirements/lambda.txt" \
    --source-version "1.0.1" \
    --aws-profile-name "kodhive_prd" \
    --watch-log-stream

Demos
======

Code and dependencies changes
-----------------------------

If both code and dependencies changed, the pipeline will publish both changes.

.. image:: https://github.com/obytes/aws-lambda-ci/raw/main/docs/images/demo_code_changed_deps_changed.gif


Just code changed
-----------------

If code changed but not dependencies, the pipeline with publish new code and the dependencies will be left intact.

.. image:: https://github.com/obytes/aws-lambda-ci/raw/main/docs/images/demo_just_code_changed.gif


Nothing changed
---------------

If both code and dependencies not changed, the pipeline will not publish anything.

.. image:: https://github.com/obytes/aws-lambda-ci/raw/main/docs/images/demo_nothing_changed.gif

