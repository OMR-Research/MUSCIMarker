.. include:: shortcuts

.. _organizing:

Organizing your work
====================

In order to make the annotation go as smoothly as possible, please make
sure to follow these guidelines for organizing and submitting your work.

The annotation comes in *packages*. Each package comes with a set of
*source images*. Using MUSCIMarker, you will create the *annotations*,
and MUSCIMarker records your actions into *annotation logs*. The package
name usually includes the day it was sent to you and some description
of where the images come from (such as the CVC-MUSCIMA dataset, or other
sources).

The structure of the package, when you get it, will be like this::

  2016-10-28_MUSCIMA/
      |
      + annotation_logs/
      + annotations/
      + source_images/
                 + music1.png
                 + music2.png
                 + music3.png
      + mff-muscima-mlclasses-annot.xml

The annotations that you create will gradually fill the ``annotations/``
subdirectory (though you currently have to navigate there manually for the first
image after opening MUSCIMarker). The name of the annotation file is derived
from the image file, only the ``.png`` suffix is changed to ``.xml``, to
correspond to the file format.

Therefore, after the annotations are finished, the package be like this::

  2016-10-28_MUSCIMA/
      |
      + annotation_logs/
      + annotations/
                 + music1.xml
                 + music2.xml
                 + music3.xml
      + source_images/
                 + music1.png
                 + music2.png
                 + music3.png
      + mff-muscima-mlclasses-annot.xml

The last thing to fill in before submitting is to provide the *annotation logs*.

Go to your home directory and find the ``.muscimarker-tracking`` folder.
(On Mac or Linux, it will be hidden; use ``ls -a`` in the terminal to see it.)
Copy this folder and paste it into the package's ``annotation_logs/`` subdirectory.
The package now looks like this::

  2016-10-28_MUSCIMA/
      |
      + annotation_logs/
                 + .muscimarker-tracking/
                                    + (lots of files)
      + annotations/
                 + music1.xml
                 + music2.xml
                 + music3.xml
      + source_images/
                 + music1.png
                 + music2.png
                 + music3.png
      + mff-muscima-mlclasses-annot.xml

The next step is to compress the completed package into a ``*.zip`` archive
(Windows: right-click, then "Archive", select ``zip`` format instead of ``rar``).

After you zip the package, send the zipped archive to ``hajicj@ufal.mff.cuni.cz``.
**Please always send this in a new email, do not send it as replies to other mails.**

