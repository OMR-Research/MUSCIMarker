.. include:: shortcuts

.. _grayscale:

Grayscale
=========

So far, you have been annotating black-and-white images (these are called
*binary* in literature, as they only consist of two colors, and can
be characterized using just 0s for black pixels -- background --
and 1s for white pixels -- foreground). Now, we proceed into the realm
of images that consist of all sorts of shades of gray (called *grayscale*).
This document will teach you how to use MUSCIMarker to annotate grayscale
images efficiently.

Why are we talking about binarization?
--------------------------------------

MUSCIMarker has tools that speed up annotation of images
with a black background.
However, these tools do not work on normal
grayscale images. The Trimmed Lasso behaves like a normal lasso
(selecting all pixels that you draw it around) without the black
background, and the Connected Component tool fails completely -- if
there is no background, the entire image is a single connected component
of the foreground.

Especially for musical scores, it is hard to automate
*binarization* -- the process of determining which pixels belong
to the background, and which do not -- of document images in general,
because the pen strokes usually come out with different intensities,
the paper is dirty, lighting is uneven, etc. In the end, really accurate
binarization is practically equivalent to annotating the score
in the first place.

Therefore, instead of supplying already binarized
images, **you will mark the background as you go**. This way, at
the cost of doing binarization together with annotation, you retain
the power of MUSCIMarker annotation tools, and the resulting annotation
will at the same time remain accurate.

.. note::

    Grayscale images harder to annotate accurately than binary (black-and-white).
    We do not expect the same level of annotation accuracy as we did for
    binary images, as that would take too long. (However, accuracy still
    matters -- it's just that in situations where symbols have e.g. unclear
    edges dissolving gradually into the background, don't sweat it too much.
    In general, making the symbols a little bit *larger* is better than
    making them smaller.

How to binarize efficiently
---------------------------

Binarization is *not* another result of the annotation. Binarization tools
just make temporary changes to the image so that you have an easier life
trying to annotate the symbols.

**Best practice 1:** First binarize a region of the image, then annotate it.

**Best practice 2:** Don't binarize too much at once. Stick to binarizing
areas that fit on your screen when you are zoomed in to annotate.

Remember: the goal is *NOT* to binarize the input image accurately. The goal
is to *annotate the symbols and their relationships*, and binarization is
a way to help you do it faster.

.. note::

    In general, binarization and annotation do not mix. If you binarize a part
    of the image, the objects and relationships that are already there will
    not be affected at all.

    This may lead to slightly counterintuitive results. If you
    annotate an object, and then mark a part of the object as background
    (and, therefore, the pixels should not participate in any future
    symbols), that part of the object will *remain* in the previously
    marked object.


Binarization Tools
------------------

MUSCIMarker gives you the following tools for binarization:

* **Background Lasso** (really easy!)
* **Region Binarization** (a little tricky)

We will now explain how to use each of these.


Background Lasso
^^^^^^^^^^^^^^^^

With the Background Lasso tool, you mark a part of the image as background.
It works like any other lasso tool. Once you release the mouse button,
the selected region will turn black and subsequently will be correctly
handled by Trimmed Lasso and Connected Components.

Region Binarization
^^^^^^^^^^^^^^^^^^^

The Region Binarization tool attempts to guess which parts of a given region
belong to the background. It guesses a cutoff intensity that should produce
a separation into foreground and background pixel intensities.

When using region binarization:

* Apply it to regions of the size that you will be annotating without moving
  around. Apply region binarization when you are already zoomed in
  at your preferred zoom for annotating.
* Don't apply it to regions that overlap with already binarized regions
  by more than a few pixels. The uniform black of the background in the
  already binarized part of the region will confuse the guessing algorithm.

The gory details, if you're interested (but you don't have to read this):

We use Otsu's binarization algorithm.
It assumes the intensity (brightness) of a pixel
comes from either a *background* source, or a *foreground* source.
Each of these two assumed sources is assumed to have a default intensity
which it prefers to assign to "its" pixels, but there is some randomness
in the process of generating intensities, so instead of the default intensity,
each pixel comes out somewhat different from the given source's default.
Think of it like throwing darts: the background source and foreground source
each have a default intensity in the middle of the dart board, and as
the darts land further from the target, the output intensity will be more
and more different from the default. Otsu's algorithm assumes

This makes Otsu's algorithm fast to compute, but it's quite fragile
when the image has varying lighting conditions, e.g. when taking a photo
under a lamp (the corners come out darker).



Discarding binarization
-----------------------

Binarization is done on the fly and does not affect the source image.
In case you want to reload the original image, before starting work
on binarization, use the **RELOAD IMG** command in the bottom bar.


