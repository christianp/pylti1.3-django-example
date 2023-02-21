Example of using PyLTI1p3 with Django and dynamic registration
==============================================================

`PyLTI1p3`_ is a Python implementation of LTI 1.3 Advantage Tool.

.. _PyLTI1p3: https://github.com/dmitry-viskov/pylti1.3

This example shows how to use PyLTI1p3 with the Django framework, and the dynamic registration extension to LTI Advantage.

You can run the tool through Docker, or by creating a Python virtualenv.

To run with Docker, execute:

.. code-block:: shell

    $ docker-compose up --build

To run with virtualenv, execute:

.. code-block:: shell

    $ virtualenv venv
    $ source venv/bin/activate
    $ pip install -r requirements.txt
    $ cd game
    $ python manage.py migrate
    $ python manage.py createcachetable
    $ python manage.py runserver 127.0.0.1:9001

Now there is game example tool you can launch into on port 9001.

Next, you must register the tool with your LTI platform.

At the moment, dynamic registration has only been tested with Moodle.

In Moodle, go to *Site administration* → *Plugins* → *Activity modules* → *External tools* → *Manage tools*.

In the *Add tool* box, enter the tool's address in the *Tool URL* field: ``http://localhost:9001/register``, and click *Add LTI Advantage*.
