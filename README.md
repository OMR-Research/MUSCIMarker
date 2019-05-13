# MUSCIMarker

Tool for annotating objects in musical scores.

**MOVED TO:** https://github.com/OMR-Research/MUSCIMarker

All new development takes place there. Please point your remotes to the
new repo.


[![Documentation Status](https://readthedocs.org/projects/muscimarker/badge/?version=latest)](https://muscimarker.readthedocs.io/en/latest/index.html)
[![Build Status](https://travis-ci.org/OMR-Research/MUSCIMarker.svg?branch=develop)](https://travis-ci.org/OMR-Research/MUSCIMarker)
[![Build Status](https://dev.azure.com/OMR-Research/MUSCIMarker/_apis/build/status/OMR-Research.MUSCIMarker)](https://dev.azure.com/OMR-Research/MUSCIMarker/_build/latest?definitionId=1)
[![Coverage Status](https://coveralls.io/repos/github/OMR-Research/MUSCIMarker/badge.svg?branch=develop)](https://coveralls.io/github/OMR-Research/MUSCIMarker?branch=develop)
[![codecov](https://codecov.io/gh/OMR-Research/MUSCIMarker/branch/develop/graph/badge.svg)](https://codecov.io/gh/OMR-Research/MUSCIMarker)


Documentation: http://muscimarker.readthedocs.io/en/latest/

## Requirements

* Python 2.7.11 and later (not 3)
* Kivy
* numpy, scipy
* lxml
* skimage

## Tutorial

...is in the documentation:  http://muscimarker.readthedocs.io/en/latest/tutorial.html

*This work is supported by the Czech Science Foundation, grant number P103/12/G084.*

## Build the distributable binary for Windows

Basically follow the tutorial from the [Kivy website](https://kivy.org/docs/guide/packaging-windows.html):

- Make sure you have all dependencies ([general](requirements.txt), [windows-specific](requirements_windows.txt)) installed, including Kivy, which is not listed directly. Check out [Travis build environment](.travis.yml) for Linux and [Azure Pipeline environment](azure-pipelines.yml) for Windows.
- From within `[GIT_ROOT]/MUSCIMarker/MUSCIMarker` run `python -m PyInstaller --name MUSCIMarker main.py`
- Navigate to the `MUSCIMarker.spec` file and add `from kivy.deps import sdl2, glew` to the top and the following two statements to the COLLECT or EXE script:
    - `Tree('[GIT_ROOT]/MUSCIMarker/MUSCIMarker')`
    - `*[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)]`
- Run `python -m PyInstaller MUSCIMarker.spec`