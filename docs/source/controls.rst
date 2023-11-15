.. All the ways of controlling MUSCIMarker

.. include:: shortcuts

.. _controls:

Controlling MUSCIMarker
=======================

Here is an overview of all the things you can do with MUSCIMarker.
This is a UI reference document -- it describes how you can interact
with MUSCIMarker, but not how to use these possibilities to get
the desired results. For that, read the :ref:`tutorial` and :ref:`instructions`.

We'll organize this description into some groups:

#. :ref:`controls_navigation`: Move and zoom the annotated image
#. :ref:`controls_fixed`: Control the application using fixed interface
   elements (mostly buttons)
#. :ref:`controls_tools`: Use tools to create and edit annotations
#. :ref:`controls_editing`: Interact with annotations



**Quick Refresher:**

    There are two kinds of annotations in MUSCIMarker: *objects* (CropObjects,
    displayed as colored rectangles) and *relationships* (displayed as lines
    connecting the CropObjects), which connect objects. Relationships
    have an orientation: they go *from* one object *to* another. (The "from"
    object gets a little square on its end of the relationship.)

    Adding objects is done primarily through *tools*, like the Trimmed Lasso
    or Connected Components. Generally, one click & drag action
    (or a one-finger touch action, on a device with a touchscreen)
    will create one new object.

    The annotations can then be *selected*. If an object is selected, it looks
    brighter. If a relationship is selected, it gets emphasized.

    New relationships can be added through keyboard shortcuts

.. _controls_navigation:

Navigating the image
--------------------

The image is your main workspace: it's where annotating *happens*.
You will need to move around the image and zoom it.
(This was covered in the tutorial. Here, we're just giving a complete verions.)

**Move.** Left-click and drag the image. The initial click must be in the black:
*outside* any annotation, in order to affect the image. (If you press down inside
the area of an annotation, that annotation will "eat" the click.)

**Zoom.** Two steps with a laptop/dekstop computer:

#. Right-click the image. A red dot will appear.
#. Left-click & Drag to zoom. It works like a pinch-to-zoom gesture: the further
   you go from the red dot, the more the image zooms in.

With a touch screen, simply use the normal pinch-to-zoom gesture. (The red dot
is like a "fake finger".)

**Center.** If you get lost or need to quickly get to a different area of the
image, click the "CENTER" button on the action bar along the bottom of the screen.


.. _controls_fixed:

Fixed interface elements
------------------------

Interface actions mainly consist of pressing buttons. As you know from
the :ref:`tutorial`, the MUSCIMarker interface has three parts that
expose ways of controlling the application: the *command sidebar* on the right,
the *tool sidebar* on the left, and the *action bar* on the bottom.

.. note::
    We call these control elements "fixed", because no matter what the state
    of the annotation, they don't change.

.. _controls_command_sidebar:

Command sidebar
^^^^^^^^^^^^^^^

This sidebar generally controls the annotation inputs and outputs: what
image you are annotating, saving & loading the annotation, selecting
the MLClass that should be annotated, hiding/showing the current annotation,
etc.

.. note::

    All file loading dialogues will be opened by default to pointing
    to the directory where the corresponding currently loaded file is
    (so, if you are loading an image, the loading dialog will show
    you images from the same directory as the image you are annotating).

We now list what the individual elements of the command sidebar do.
Going from the top down:

**Select MLClassList** The MLClass list is where we define what the symbol
classes are. This button shows a file loading dialog where you can choose
which set of symbol classes to use. (The name of the last loaded MLClass list
file is displayed in grey beneath the topmost buttons.)

.. danger::

    Changing the MLClassList invalidates all of the current annotation!
    Do not do this unless explicitly instructed to. MUSCIMarker ships with
    a default MLClassList file that should be good enough.

**Select Grammar** The grammar defines what symbol relationships are
possible. This button shows a file loading dialog where you can choose
which set of rules to use.

.. danger::

    Changing the grammar invalidates all the current relationships between
    the annotated objects! Do not do this unless explicitly instructed to.
    MUSCIMarker ships with a default grammar that should be good enough.


**Select MLClass** Under the "Select MLClass" label, the name of the current
class is set. New CropObjects that you add to the annotation will belong
to the current class. Clicking on the button with the class name will open
a list of available classes. (You can scroll or click+drag the list.)

Selecting from this list is *not* the only way to set the current class.
You can also *clone* the class of a selected CropObject -- take something
you already annotated and set *its* class as the current class
(see :ref:`controls_selection_shortcuts`).

**Select image file** If you want to change the image that you are annotating,
click this button. A file loading dialog will appear; navigate to the desired
image and select Load (or double-click the filename).

.. caution::

    Loading a new image will clear all current annotations. Make sure
    you have exported your work!

**Import CropObjectList file** The CropObject list file is an XML file that
contains the current state of the annotations: all the selected objects
and relationships between them. This button opens a file loading dialog
that allows you to import a CropObject list file; navigate to the desired
file and select Load (or double-click the filename).

.. important:: **This is the way to load your previous work.**

The name of the last loaded MLClass list file is displayed in grey beneath
the CropObjectList import/export buttons.

.. caution::

    Loading a new CropObject list will clear all current annotations. Make
    sure you have exported your work!

**Export CropObjectList file** Save the current state of the annotation
to a CropObject list file (see the explanation for Import CropObjectList file).
A file save dialog will appear. A file name is suggested automatically
(in the white text input field, bottom of the dialog), to correspond to the
filename of the current image.

.. important:: **This is the way to save your work.** Do this often.


**Counters.** Next, you see how may objects and relationships between
objects (Attachments) are currently annotated. If you're not sure that
your action actually added or deleted some object or reltionship, take
a look at the numbers.


**Clear CropObjects.** Delete all current annotations. A confirmation dialog
will pop up, so that you don't click this by accident. This cannot be undone!


**Hide/Show CropObjects.** Hiding CropObjects means that you will not see
them and won't be able to interact with the annotations. You will, however,
still be able to interact with the relationships. This may be useful when
there is a lot of CropObjects and you interact with them accidentally.

**Hide/Show Relationships.** Just like the previous buttons, but operates
on the relationships. Useful if the Relationships get in the way of working
with CropObjects.


.. _controls_action_bar:

Action Bar
^^^^^^^^^^

The *Action bar* on the bottom provides some convenience commands that do not
interact with the state of the annotation. Going from left to right:

**Center** If you get lost while zooming around the image, this button
will center the image and scale it back to its initial size.

**Backup** Manually create a snapshot of the current state of the application.
Backups happen automatically in the background every 20 seconds (you can change
that in the Settings).

.. warning::

    **This is not a substitute for saving your work!** Backup and Recover
    are here to help with application crashes. There is only ever one snapshot
    saved deep among the internal files of MUSCIMarker, so it's not a poor
    man's Undo, either!

**Recover** Load the annotation state from the snapshot. Try to do this when
you re-open MUSCIMarker after a crash - it might help you not lose some work
you didn't save using the "Export CropObjectList file" dialog. However,
there is no guarantee that this will work! Perhaps the auto-snapshot was
being saved while MUSCIMarker was crashing, so it can't be recovered!
**The Backup/Recover mechanism is not a substitute for saving your work.**

**Settings** Opens the Settings panel. Currently, you do not ever need to go
there.

**Exit** This is the correct way of exiting the application.


.. _controls_tools:

Tools
^^^^^

The *Tool sidebar* lists the available annotation tools. Tools allow you
to add objects and relationships and other interaction with the image
and annotations.

.. tip::

    If you are not sure how a tool works from the description,
    experiment with it on the default image.

Only one tool can be selected at a time. If there are no selected annotations,
pressing "Escape" unselects the current tool.

**Keyboard shortcuts.** You can use the numbers 1, 2, etc. to select the first,
second, etc.-th tool from the top.

We will now describe the available tools. Going from the top down:

**Trimmed Lasso** Draw a lasso around an object in the image. Once you release,
adds the selection as a new CropObject annotation. Ignores background (black):
you do *not* have to accurately trace around an object's border with
the background. However, you need to be accurate when objects overlap.
See the :ref:`guidelines`.

**Connected Component** Draw a rectangle. Upon release, will add a CropObject
that consists of all "connected components" of the foreground: contignuous
non-black segments. This allows quickly adding CropObjects when the visual
object that you want to mark does not overlap any other visual objects
in the image. If it does overlap, however, you will need to use the Trimmed
Lasso tool, because the object needs to be accurately marked in the overlapping
part.

.. note::

    When you first use this tool after loading an image, it will take
    a while to pre-compute where the connected components are. Subsequent
    uses, however, will be quick.


**Object Selection** Draw a lasso and select all CropObjects that overlap
this rectangle. Handy for adding relationships: quickly select groups
of CropObjects with this tool and press "p" to create relationships.

The selection can be made *active* in the Settings: this means it will
light up selected symbols as you go.


**Relationship Selection** Draw a lasso, find all CropObjects that overlap
this rectangle (like the Object Selection tool), and select their *Relationships*.
This is useful for mass-editing Relationships.

.. note::

    It's not quite perfect: this way, it only allows you to select either
    *all* the relationships of an object, or *none* of them.

**Parse** Draw a rectangle and apply relationships to the set of all CropObjects
that overlap this rectangle. Handy for adding relationships without having
to press "p" over and over again.


**Eraser Lasso** Sometimes, your hand slips when annotating and you mark some
extra pixels which should not be a part of the object. This tool enables correcting
that:

1. Select (only) the object you need to fix,
2. Draw a lasso around the parts that you want to throw out.

Use `i` (inspection) to check the results.


**Plus Lasso** Sometimes, your hand slips and you don't mark pixels that should
be a part of the object you're working on -- the opposite of Eraser Lasso.
This tool enables you to add more pixels to an object:

1. Select (only) the object you need to fix,
2. Draw a lasso around the parts that you want to add to the object.

Use `i` (inspection) to check the results.

Especially for the Plus Lasso, make sure that when you are using it,
no other objects are selected, except for the one you want to edit.


.. _controls_selection:

Selecting annotations
---------------------

Annotations - both objects and relationships - can be selected.
Selecting an annotation (or several) opens up new actions that
can be applied to the selected annotations: these range from a simple
delete to "guessing" new relationships.

How to control what is selected and what isn't?

**Click an annotation.** This is the basic operation that applies to both
objects and relationships. Clicking toggles whether an annotation is selected
(clicking a not-selected annotation selects it, clicking a selected annotation
unselects it).

.. tip::

    As the objects are heaped one on top of the other, sometimes
    you cannot click an object because it is entirely hidden by another
    one. However, if you select the top annotation and pres "b", it gets sent
    to the bottom and you will be able to click the annotation you want.

    If *relationships* are what makes the annotation un-clickable, you can
    hide them with the "Hide Relationships" button in the command sidebar.

**Tools for selecting.** The "Obj. Select" and "Rel. Select" tools are good
for mass-selecting objects and relationships in a given region.

**Deselecting** Press "Escape" to deselect all annotations. (Pressing it again
will attempt to unselect the current tool as well.)

Once you select an object, a brief description appears in the bottom part
of the command sidebar - the *info panel*. There, you can verify whether
you really selected what you wanted to select -- or, that *nothing* is selected,
in which case the info panel will be empty.

.. _controls_editing:

Editing selected annotations
----------------------------

Once you are happy with which annotations are selected, you can use some
keyboard shortcuts that act on the selected annotations. Some keyboard
shortcuts only work on *objects*, and some only work on *relationships*.
A few work on both:


=============      ===========================================================
**Escape**         De-select everything in the selection.
**Backspace**      Delete the selected annotations. (Careful! No Undo!)
=============      ===========================================================


.. note::

    Deleting an object also deletes all its relationships.


.. _controls_selection_shortcuts_cropobjects:

Editing a selection of objects
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The following keyboard shortcuts work on selected objects:

=================   ================================================================
**alt+Backspace**   Delete all relationships of selected objects.
**p**               Find all possible relationships among the selected objects.
**m**               Merge: adds a new object with the current label, and deletes
                    the selected objects. (Useful for annotating large objects
                    as parts.)
**shift+m**         Merge (safe): adds a new object with the current label and
                    does *not* delete the selected objects. Also automatically
                    attempts discovering relationships, like pressing **p**.
                    (Useful for key signatures, repeats, texts, etc.)
**c**               Manually change the class of a selected object.
**shift+c**         Sets the app's current class to the class of a selected object.
**ctrl+shift+c**    Apply the app's current class to all selected objects.
**a**               Create a relationship from the first to the second
                    selected object. Don't use this unless you can't use **p**.
**d**               Remove a relationship from the first to the second
                    selected object.
**b**               Send selected objects backward, so that it exposes the objects
                    that were lying underneath. (Useful when a large object
                    overlaps smaller ones, like text.)
**i**               Inspect the selected object. **(New!)** A popup appears with
                    the object's exact position highlighted.
**alt+h**           Hide/Show the selected objects' relationships.
=================   ================================================================

.. note::

    Also, notice what you *cannot* do with annotations: move and stretch them!

    (There are good reasons why this is not possible: if we allowed these actions,
    we would often get into situations where we would have to guess which pixels
    should be a part of the manipulated object and which should not. This would
    greatly deteriorate the quality of the data.)


.. _controls_selection_shortcuts_graph:

Editing a selection of Relationships
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There are currently no keyboard shortcuts available for manipulating
selected relationships.


.. _controls_shortcuts_global:

Global keyboard shortcuts
-------------------------

These shortcuts work if no object or relationship is selected, or if
the given selection is not supposed to react to the shortcut.

=================   ================================================================
**v**               Validate the current annnotation. Finds inconsistencies in how
                    relationships are being assigned to objects.
**c**               Open symbol class selection dialog. (See below.)
**o**               Open ID-based object selection dialog. (See below.)
**alt+h**           Hide/Show all relationships.
**1, 2, ...**       Select the n-th tool from the top.
**alt+shift+b**     Barline to measure separator automation.
=================   ================================================================


.. _controls_dialog_mlclass_selection:

MLClass selection dialog
^^^^^^^^^^^^^^^^^^^^^^^^

The MLClass selection dialog enables quickly selecting new MLClasses
by typing their names. The dialog will show you the suggested symbol
in the input field and a list of available symbols with the given prefix
(truncated to 5) below.

**Controlling:**

Type to enter text.

Enter to confirm, Escape to cancel (or just press the buttons).

Press "tab" to have the dialog guess the next part of
the symbol name (it's never wrong, but sometimes it might not be able to
come up with any guess at all). Try pressing tab when trying to get letters!
It should speed up the process considerably.

If there are symbols where the name of one is a prefix of the other,
such as ``repeat`` is a prefix of ``repeat-dot``, you need to get the whole
word there (``repeat``) to select that MLClass. You can still use "tab"
to get there.


Objid selection dialog
^^^^^^^^^^^^^^^^^^^^^^

The ``objid``-based selection dialog enables quickly selecting CropObjects
using their unique identifier. Type in the numbers, separated by whitespace
(you can also add commas, semicolons, etc.). Upon confirmation, these objects
will be selected (and *only* these objects - previous selections will be
canceled).

**Controlling**

Type to enter text.

*Example:* ``123, 125, 126, 128`` *or* ``123 125 126 128``

Enter to confirm, Escape to cancel (or just press the buttons).

As opposed to the MLClass selection dialog, pressing "tab" does nothing.


Barlines to measure separator automation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Pressing ``alt+shift+b`` will cause all barlines (``thin_barline``,
``thick_barline``, ``dotted_barline``) that currently have no inlinks
to get a ``measure_separator`` parent.


Automated checks for objects with holes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes, there are mistakes in annotation that are hard to see
from the bounding boxes: the annotator gets the bounding box correctly,
but leaves out parts of the symbol itself from the mask. To discover
these cases, there are two shortcuts:

* ``alt+shift+t`` finds all objects where more than a given proportion
  of foreground pixels in the object's bounding box is not a part of
  its mask,
* ``alt+shift+r`` finds all objects where more than a given proportion
  of foreground pixels in the object's bounding box is not a part of
  *any* object's mask.

Both proportions, for the non-exclusive foreground and for the exclusive
foreground counts, can be set in the Settings.

Each check serves a slightly different purpose. The first check (the
non-exclusive one) will show you symbols like flags, slurs, beams with
a significant slope, etc. Sometimes, it is informative to see which objects
are *not* highlighted and should be -- this helps to discover flags
where the stem is erroneously marked as part of the flag. Slurs that
clearly have other objects in their bounding box but don't light up
even with low thresholds are indicative of someone not marking out
the concave part of the slur and instead letting the Trimmed Lasso
take a "shortcut".

The second check is useful for straight-out mistakes where the annotators
just did not mark a part of an object that clearly does not belong to any
other object.


Automated checks for disconnected objects
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To find all objects that consist of more than one contiguous "blob",
use ``alt+shift+d``. To exclude from this search all object that have
some other objects attached, such as key signatures or time signatures,
use ``alt+shift+s``. This avoids "false alarms", also from texts, but
on the other hand does not cover noteheads or stems with tremolos.
The recommendation is to use both: first make sure there are no ``alt+shift+s``
problems (except for those where the object is legitimately split
into more parts, such as because of staff removal mistakes), then use
``alt+shift+d`` to find the noteheads and other symbols that did not
show up on ``alt+shift+s`` due to having outlinks.