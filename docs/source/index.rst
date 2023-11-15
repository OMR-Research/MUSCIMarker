.. MUSCIMarker documentation master file, created by
   sphinx-quickstart on Wed Sep 21 12:04:51 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. include:: shortcuts

.. _index:

MUSCIMarker
===========

MUSCIMarker is an app that marks object locations on the page.
The name stands for "MUsical SCore Image Marker": the primary
purpose of the app is to mark locations of notation symbols
in images of musical scores. (Although it can in principle support
any kind of 2-D object marking.)

.. image:: images/screenshots/fancy_screenshot.png

.. note::

    This work is supported by the Czech Science Foundation,
    grant number P103/12/G084.


Installation
------------

The instructions are here: :ref:`installation`.

.. note:: As it stands now, we don't have installation packages that would
          work for people who don't have Python. We're working on it, though.

.. note:: You need Python 2.7 -- although most of MUSCIMarker should
          be compatible with Python 3, we haven't yet tested this. (It's fine
          if you have a Python 2 virtual environment such as conda -- see
          :ref:`installation`.)


What now?
---------

Once you install MUSCIMarker, go through the :ref:`tutorial`.
It will gently teach you how to use MUSCIMarker, and introduce the most
important concepts.

Once you are done with the tutorial, the :ref:`instructions` will
give you the details of how to annotate music notation symbols.

A complete description of what can be done with MUSCIMarker is available
in :ref:`controls`.


Contact
-------

MUSCIMarker is developed at the |UFAL|_.
Usage questions should be addressed to ``hajicj@ufal.mff.cuni.cz``
and bugs/crashes should be reported through the project's
|GitHub|_ issue tracker.



Contents:
---------

.. toctree::
   :maxdepth: 2
   :numbered:
   :titlesonly:

   Installation <installation>
   Tutorial <tutorial>
   Starting MUSCIMarker <running>
   Annotation instructions <instructions>
   Organizing your work <organizing>
   MUSCIMarker complete interface <controls>
   Grayscale images <grayscale>

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

