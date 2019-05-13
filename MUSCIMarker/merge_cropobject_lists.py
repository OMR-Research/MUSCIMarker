#!/usr/bin/env python
"""This is a simple script that merges a number of CropObject list
files into one."""
from __future__ import print_function, unicode_literals
import argparse
import codecs
import logging
import time

from muscima.cropobject import merge_cropobject_lists
from muscima.io import  parse_cropobject_list, export_cropobject_list

__version__ = "0.0.1"
__author__ = "Jan Hajic jr."


def build_argument_parser():
    parser = argparse.ArgumentParser(description=__doc__, add_help=True,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('-i', '--inputs', nargs='+', required=True,
                        help='Input CropObject lists. Will be appended'
                             ' in the order in which they are given.')
    parser.add_argument('-o', '--output', required=True,
                        help='Output file for the merged CropObject list.')

    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Turn on INFO messages.')
    parser.add_argument('--debug', action='store_true',
                        help='Turn on DEBUG messages.')

    return parser


def main(args):
    logging.info('Starting main...')
    _start_time = time.clock()

    logging.warning('Merging CropObject lists is now very dangerous,'
                    ' becaues of the uid situation.')

    inputs = [parse_cropobject_list(f) for f in args.inputs]
    merged = merge_cropobject_lists(*inputs)
    with codecs.open(args.output, 'w', 'utf-8') as hdl:
        hdl.write(export_cropobject_list(merged))
        hdl.write('\n')

    _end_time = time.clock()
    logging.info('merge_cropobject_lists.py done in {0:.3f} s'.format(_end_time - _start_time))


if __name__ == '__main__':
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)
    if args.debug:
        logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)

    main(args)
