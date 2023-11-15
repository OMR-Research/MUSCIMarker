.. include:: shortcuts

.. _tutorial:

Tutorial
========

Welcome to the MUSCIMarker tutorial! Here, you will learn
how to use MUSCIMarker to annotate symbols in a musical score.

.. .. note:: The app is in its alpha stage. There are inconveniencies,
              bugs, weird behavior, etc. -- we'd be happy if you report
              these to |contact_email|.

.. note::

    The interface in some screenshots is a little outdated (back to v0.9),
    but all the interface elements that the tutorial mentions are still
    available and in the same space.

Start MUSCIMarker
-----------------

Follow the startup instructions in :ref:`running`.
If you have MUSCIMarker installed in a virtual environment, don't forget
to activate the environment.

After navigate to the folder that contains the ``main.py`` file in the console
and runing::

  python main.py

A window with the app will appear:

.. image:: images/screenshots/first_startup_screen.png

Let's walk through the interface.
The main part in the middle is occupied by the image that we annotate:

.. image:: images/screenshots/ui_overview_image.png

For marking the symbols in the score, you'll use a bunch of tools:

.. image:: images/screenshots/ui_overview_toolkit.png

To load an image, export the annotation, or to import a different
annotation, use the commands on the right-hand side:

.. image:: images/screenshots/ui_overview_commands.png

There are some convenience commands along the bottom of the screen,
such as centering the image, backing up your work, or accessing
the app settings:

.. image:: images/screenshots/ui_overview_morecommands.png

And that includes the all-important Exit button!

.. image:: images/screenshots/ui_overview_exit.png


Explore the image
-----------------

You can zoom and move the image around. MUSCIMarker works both on a desktop
and on a smartphone or tablet, but the usage is a little different.

.. .. warning:: There is currently no tested implementation of keyboard shortcuts
               on mobile platforms!

On a tablet, the image responds to the usual touch commands: drag to move
and pinch to zoom. On a desktop, you can drag & drop to move the image around
as usual. For zooming, we'll need to "simulate" one finger by right-clicking
anywhere on the image. A red dot should appear:

.. image:: images/screenshots/ui_moving_rightclick.png

Dragging now zooms the image, instead of moving.

.. image:: images/screenshots/ui_moving_clickanddrag.png

...

.. image:: images/screenshots/ui_moving_zoomed.png

The red dot is like having one finger pressed against that point in the image,
and dragging with the mouse works like the second
finger in the pinch-to-zoom gesture.
Play around with the desktop zoom for a bit, you'll get the hang of it soon!

Once you're done zooming, just left-click the red dot -- the "fake finger" --
to exit zooming mode.

.. image:: images/screenshots/ui_moving_stopzooming.png

If you get lost -- hey, it happens -- or anytime you want to jump
back to the original scale, use the CENTER command on the bottom pane.

.. image:: images/screenshots/ui_moving_center.png

The annotated image will scale back to its original size and center
itself in the editor window.

You'll probably be spending most of your time with MUSCIMarker zoomed
in, so spend a minute getting used to navigating the image before we
proceed to the next step: annotating.

.. _tutorial_objects:

Annotate objects
----------------

Annotating objects means marking regions of the image as objects from a certain set.
In this tutorial, we'll the objects are "primitives" that make up common
western music notation. The set of possible notation symbols has been
pre-loaded and we already have an image, so we can get right to it!

First, zoom in the image to a level where you can comfortably see all the details.
(Don't forget to "unclick" the red spot afterwards.)

Now, choose an annotation tool from the toolkit. No punches pulled,
go for the Trimmed Lasso tool -- it's the most powerful one you get,
and you'll be probably spending most of your precious annotator time
with that tool. So, let's get used to it right away.

.. image:: images/screenshots/ui_annot_selecttool.png

The selected tool is now highlighted.

Check which symbol type is selected:

.. image:: images/screenshots/ui_annot_symboltype.png

Select a different symbol type to annotate by clicking on the
current symbol type (it works like a button) and then choose
from the drop-down. Drag or scroll to move the drop-down around.

.. image:: images/screenshots/ui_annot_selectsymbol.png

To mark a symbol with the trimmed lasso, just draw the lasso around the object.
Don't worry about where you're going in the black area: this tool ignores
ignores black parts.

.. image:: images/screenshots/ui_annot_trimmedlasso_drawline.png

The bounding box of the selected symbol will appear (it's a bit transparent,
because sometimes they overlap and you need to see what's in the image
underneath).

.. image:: images/screenshots/ui_annot_trimmedlasso_boxappears.png

However, when symbols overlap and you need to draw the lasso through a white
 area, trace the symbol contour that you think is there very accurately.

.. image:: images/screenshots/ui_annot_trimmedlasso_careful.png

Zoom in closer if you are not sure that the line is exactly where
you want it. Accuracy matters.

Try annotating a bunch of objects!

.. tip:: Find out more about the available tools here: :ref:`controls_tools`


Save and load your work
-----------------------

Once you have annotated something, use the ``Export CropObject List``
button.

.. image:: images/screenshots/ui_saveload_exportbutton.png

Navigate to the folder where you want to save the file.
The proposed filename (ending with ``xml``) is derived from the current
image file.

.. image:: images/screenshots/ui_saveload_dialogue.png

**Save often (every, let's say, 3-5 minutes) - there is no "Undo"!**

You can then load the exported annotations in the same way, using
the ``Import CropObject List`` button, right above the ``Export`` button.

.. image:: images/screenshots/ui_saveload_importbutton.png


.. _tutorial_relationships:

Annotating Relationships
------------------------

The *objects* that we have annotated so far have some *relationships*
to each other. For instance, a notehead may have an attached stem, a staccato
dot, or it may also come with a beam that you need to be aware of in order
to interpret the note correctly.

Let's annotate a relationship of objects. Choose two objects that you have
annotated by clicking on them:

.. image:: images/screenshots/ui_annot_clicktoselect.png

The selected objects will brighten up. Now, press **a**:

.. image:: images/screenshots/ui_annot_relationship.png

A relationship was formed between the two symbols!

Note the little square in one of the symbols. A relationship leads *from*
one object *to* another -- it has an *orientation*, like an arrow.
The "from" object is the one with the square (the imaginary arrow is pointing
*away* from the square). The order of objects on the info panel is also
a hint about how the relationship forms.

.. image:: images/screenshots/ui_annot_relationshipdirection.png

Relationships with Rules
^^^^^^^^^^^^^^^^^^^^^^^^

Although you could use what you learned to just connect everything,
that would not be particularly helpful. Object sets come with some
rules that describe how objects form relationships.
For instance, the standard rules of writing music notation say that
a stem should be connected to a notehead, or that a repeat sign consists of
a thin barline, a thick barline, and some dots. For the default set
of musical symbols, these rules also come built-in with MUSCIMarker.

There is a lot of relationships involved in music notation, so in order
to make it quicker to annotate, you can add many at once! Go ahead and
select all symbols that are related to our notehead:

.. image:: images/screenshots/ui_annot_allrelated.png


Now, press **p**:

.. image:: images/screenshots/ui_annot_parsed.png

MUSCIMarker checked which selected symbol pairs can form
a relationship, and added all these potential relationships.
(The objects automatically unselect. That's to make workflow easier:
after creating relationships among one set of symbols, you
will probably be creating relationships for a different group
of symbols.)

The **p** is mighty useful for adding the right relationships, and adding
many of them with one keystroke. However, take care not to create
*extra* relationships that should not be there! MUSCIMarker only knows
"noteheads connect to stems", but not "only one stem per notehead"
so if you select two noteheads and two stems in hopes of doing more at once,
this will happen:

.. image:: images/screenshots/ui_annot_extrarelationships.png

(This screenshot is done with auto-deselection off, so that the selection
leading to problems is obvious.)

.. note:: By the way, a rule saying "only one stem per notehead" would not
          be correct. Can you figure out why?

.. tip:: Building musiclal notation relationships correctly is described in
         the :ref:`instructions_notes` section of the :ref:`instructions`.


Delete an annotation
--------------------

If you make a mistake, don't panic! The annotations can be removed.
Unselect any tool you're using and left-click on the symbol.
This will mark the symbol as *selected*.
On the screen, it will become highlighted, and some information about the
symbol will be shown on the bottom of the right-hand panel.

.. image:: images/screenshots/ui_delete_selectedsymbol.png

Now, press backspace (not delete, backspace). The object will disappear
and the CropObject counter on the right will go down by 1.

.. note::

   Whenver a tool is selected, all mouse activity inside the image
   is handled by the tool. So if you hadn't deactivated the tool before
   selecting the object, the click would be caught and interpreted as
   a very small lasso. (This is because when you want to annotate
   a symbol, nothing you have previously done should get in the way.)

Just like objects, you can also select relationships by clicking on them.



Other stuff
-----------

There are some other useful operations MUSCIMarker allows you to do:


Annotate things that don't fit on the screen
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes you need to zoom in a lot to annotate overlapping symbols
accurately, but then the symbol does not fit on the screen. (This mostly
happens with barlines and ties/slurs.) What now?

The symbols support a *merge* operation: you can mark it in parts and then
join them into one. Marking the parts is exactly the same as marking anything
else: for the time being, the program will think there are, let's say,
three barlines. However, we then select the parts and press ``m``. Voila:
they merge! Make sure the parts overlap, though: otherwise, the merged symbol
would have gaps.



Load a different image
^^^^^^^^^^^^^^^^^^^^^^

It's analogous to how saving works, just use the ``Select image file``
button on the right.

.. image:: images/screenshots/ui_saveload_image.png

Again, just navigate to the desired image, click it and click ``Load``.
Quite simple, eh? Remember to export your annotations before you load
a new image, though: once an image is loaded, all the annotations are
cleared (they referred to the previous image, so it doesn't make any
sense to leave them with the new image).