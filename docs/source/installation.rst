.. include:: shortcuts

.. _installation:

Installing MUSCIMarker
======================

The installation instructions should work regardless of platform,
thanks to the magic of Anaconda. The operating system-dependent part
is covered in Kivy's installation instruction (see below).

These instructions are written so that you don't need admin access
and don't even need to be any kind of IT person.

.. note::

  If you have a problem during the installation process, don't hesitate
  to contact us at ``hajicj@ufal.mff.cuni.cz``. Try to include
  "MUSCIMarker install error" in the subject line, please: it will
  make us get back to you sooner!

During installation, you will need to use the *command line*.
On Windows, this is called the Command Prompt:
the program name is ``cmd``, you can search for it from the Start menu
in Windows 7 or with the magnifying glass from Windows 10.
On Linux and OS X, it's the terminal and we sort of assume you
know how to find it on these systems. ;)

.. note::

  Using the command line consists of typing in commands and running
  them with the Enter key. Don't worry if line wrap cuts
  the command in two, it's your keystroke that matters.


Install Anaconda
----------------

The first step is to install |Anaconda|_. MUSCIMarker runs for Python 2.7,
so either get Anaconda2, or create a Python 2.7 environment. Downloading
and installing Anaconda should take about 15-20 minutes on a fast connection.
During installation, unless you know what you are doing, use the defaults
(install for current user only, add to PATH, make it the default Python, etc.).

If you want Anaconda3 with a Python 2 environment, open the command line
after installing Anaconda and type::

  conda create -n py27 python=2.7 anaconda

This is going to take some 15 - 20 minutes again, as it basically
re-downloads and installs Anaconda2.

Make sure you remember whether you are using the "plain" Anaconda2, or
whether you are using Anaconda3 with a Python 2 environment.
Change to the right environment now.

Install Kivy
------------

Installation instructions for Kivy for your platform are on the Kivy website:

|KivyInstall|_

Follow the instructions for your operating system.
Don't be scared, it should actually go pretty well. MUSCIMarker does
not require ``gstreamer``, so you can skip that part of the requirements
(as applicable to your platform).

Install git
-----------

If you're not in the command line already, open it and send the command::

  conda install git

This one takes some 3-5 minutes.

Install the muscima package
---------------------------

MUSCIMarker uses this package for dealing with the annotation files.
Get it like this::

  git clone https://github.com/hajicj/muscima
  cd muscima
  python setup.py develop

That's all the prerequisites, and now you can install MUSCIMarker itself.

Install MUSCIMarker
-------------------

MUSCIMarker is installed through the Git source control system. It's pretty
straightforward. The minimum interaction involves only one extra command
on your part that ensures your version of MUSCIMarker is up-to-date. Plus,
if something screws up, it's easy to go back to a functioning version,
and it's equally easy to reinstall. You do not need any ``git`` knowledge,
just run the commands below.

To install the program, still in the command line::

  git clone https://github.com/hajicj/MUSCIMarker

MUSCIMarker should now be installed in your home directory, in a subdirectory
called ``MUSCIMarker``.

You can verify the installation by running::

  cd MUSCIMarker/MUSCIMarker
  python main.py

Right here, you should be able to continue with the :ref:`tutorial`.

(For the curious: the ``cd`` command means "(c)hange (d)irectory".
Typing a name goes down into the directory (or more: ``cd MUSCIMarker/MUSCIMarker``
goes down two levels, both named ``MUSCIMarker``).
Two dots (``cd ..``) means going one level up in the directory tree.)


Running MUSCIMarker
-------------------

When you want to run MUSCIMarker again:

#. Open the command line.
#. Only if you made the special Python 2 conda environment: ``source activate py27``
#. ``cd MUSCIMarker``
#. ``git pull`` to update to the latest version.
#. ``cd MUSCIMarker`` again (there are two directories called
   ``MUSCIMarker``, one inside the other).
#. Run ``python main.py`` and the MUSCIMarker window should open.

If you are not sure that the ``git pull`` step finished successfully,
try running ``git pull`` again. If your MUSCIMarker is correctly
updated, it should tell you that it is ``already up to date``.


What could go wrong?
--------------------

On some systems, we have encountered problems during
installation. We list these problems and give solutions whenever we have them.

OpenGL version requirements
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Kivy requires OpenGL 2.0 and above. If you run MUSCIMarker and encounter
an error message saying that only OpenGL 1.1 can be found, it could
be caused by (a) outdated graphics drivers, (b) the ``multisample`` kivy
configuration parameter. The solution to (a) is to update your drivers.
The solution to (b) means opening ``.kivy/config.ini``, find the ``multisamples``
line in the ``[graphics]`` section and set it to ``multisamples = 0``.


No valuable window provider
^^^^^^^^^^^^^^^^^^^^^^^^^^^

In one case, kivy couldn't get SDL2 to open a window. In this case, the solution
was to install the ``gstreamer`` dependency (see |KivyInstall|_) and add the
``gstreamer`` directory to the ``PATH`` variable. It's a problem probably
 caused by conflicting versions of ``libpng16_16.dll``.

Old version of MKL in system DLL path
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If ``numpy`` import fails on ``multiarray.so``, one potential cause
may be a version conflict with Intel's MKL library: if there is MKL on
the system DLL path (like: ``C:\Windows\system32\mkl_intel_thread.dll``),
Windows finds it first and there is no way to tell it to ignore it and
go find Anaconda's MKL. On Linux and OS X, you can use the ``nomkl``
conda package, but there is no math library other than MKL for Anaconda's
``numpy`` binaries to link to on Windows.

We haven't been able to solve this problem yet. A possible solution is
to track down whichever application felt the need to install MKL into
the system path and move the DLLs there. However, this may easily result
in system breakage: create arecovery point first!
