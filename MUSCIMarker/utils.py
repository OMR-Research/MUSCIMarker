"""This module implements a class that..."""
from __future__ import division
from __future__ import print_function, unicode_literals

import codecs
import logging
import os
from builtins import object
from builtins import str
from math import floor, ceil

import numpy
import skimage.measure
from kivy.core.window import Window
from kivy.properties import ObjectProperty, StringProperty, BooleanProperty, NumericProperty
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from muscima.cropobject import CropObject
from past.utils import old_div
from skimage.draw import line


__version__ = "0.0.1"
__author__ = "Jan Hajic jr."

##############################################################################
# Useful keyboard key/scancode to string conversions.
#
key2codepoint = {
    8: 'backspace',
    27: 'escape',
}

scancode2codepoint = {
    42: 'backspace',
    41: 'escape',
}

##############################################################################
class KeypressBubblingStopperBehavior(object):
    """When mixed into a Widget, will stop Window keypress events
    from bubbling through the given Widget. However, you must provide
    the binding explicitly.

    >>> # Assuming class MyWidgetWithStopper(KeypressBubblingStopperBehavior, Widget):
    >>> class MyWidgetWithStopper(Widget):
    ...     def on_key_down(self):
    ...         pass
    ...     def on_key_up(self):
    ...         pass
    ...
    >>> def example():
    ...     w = MyWidgetWithStopper()
    ...     Window.bind(on_key_down=w.on_key_down)
    ...     Window.bind(on_key_up=w.on_key_up)
    ...     # Do something...
    ...     # Before destroying the widget:
    ...     Window.unbind(on_key_down=w.on_key_down)
    ...     Window.unbind(on_key_up=w.on_key_up)
    ...

    The purpose of this mixin is basically to prevent copying these
    two methods over and over.
    """
    def on_key_down(self, window, key, scancode, codepoint, modifier):

        logging.info('KeypressBubblingStopper: stopping key_down {0}'
                     ''.format((key, scancode, codepoint, modifier)))
        return True

    def on_key_up(self, window, key, scancode, *args, **kwargs):
        logging.info('KeypressBubblingStopper: stopping key_up {0}'
                     ''.format((key, scancode)))
        return True



def keypress_to_dispatch_key(key, scancode, codepoint, modifiers):
    """Converts the key_down event data into a single string for more convenient
    keyboard shortcut dispatch.

    :returns: The dispatch key in format ``109+alt,shift`` -- key number, ``+``,
        and the modifiers joined by commas.
    """
    if modifiers:
        return '{0}+{1}'.format(key, ','.join(sorted(modifiers)))
    else:
        return '{0}'.format(key)


##############################################################################
# File choosing.
# Implementation derived from example at:
# https://kivy.org/docs/api-kivy.uix.filechooser.html

# Default paths
if not 'MFF_MUSCIMA_ROOT' in os.environ:
    MFF_MUSCIMA_ROOT = os.path.join('~', 'MFF-MUSCIMA')
else:
    MFF_MUSCIMA_ROOT = os.environ['MFF_MUSCIMA_ROOT']
MFF_MUSCIMA_SYMBOLIC = os.path.join(MFF_MUSCIMA_ROOT, 'Symbolic')
MFF_MUSCIMA_XML = os.path.join(MFF_MUSCIMA_ROOT, 'XML')


class FileLoadDialog(FloatLayout):
    load = ObjectProperty(None)
    cancel = ObjectProperty(None)
    default_path = StringProperty(MFF_MUSCIMA_SYMBOLIC)
    #
    # def on_key_down(self, window, key, scancode, codepoint, modifier):
    #     return True
    #
    # def on_key_up(self, window, key, scancode, *args, **kwargs):
    #     return True


class FileNameLoader(FloatLayout):
    """Generic view to use for file loading dialogues.
    Bind to its ``filename`` property to do something useful
    in the controller (App).

    The ``force_change`` property is a workaround for firing
    reload actions even when the file does not change. This is
    by default on, which is useful for debugging but not much more.
    """
    filename = StringProperty('None')

    force_change = BooleanProperty(True)
    '''If set, will change the filename to ``''`` before loading
    the new one, so that all callbacks bound to the filename are fired.
    However, they are fired *twice* this way, which is less than optimal.'''

    def dismiss_popup(self):
        # Window.unbind(on_key_down=self._popup.content.on_key_down)
        # Window.unbind(on_key_up=self._popup.content.on_key_up)
        self._popup.dismiss()

    def show_load(self, path=None):
        logging.info('FileNameLoader: Asked for file loading...')
        logging.info('FileNameLoader: Got path: {0}'.format(path))
        if path is not None:
            content = FileLoadDialog(load=self.load,
                                     cancel=self.dismiss_popup,
                                     default_path=path)
        else:
            content = FileLoadDialog(load=self.load,
                                     cancel=self.dismiss_popup)
        # Window.bind(on_key_down=content.on_key_down)
        # Window.bind(on_key_up=content.on_key_up)

        self._popup = Popup(title="Load file", content=content,
                            size_hint=(0.5, 0.8))
        self._popup.open()

    def load(self, path, filename):
        logging.info('FileNameLoader.load: Path {0}, selection {1}'.format(path, filename))
        full_filename = os.path.join(path, filename[0])
        if not os.path.exists(full_filename):
            raise ValueError('Selected nonexistent file: {0}'
                             ''.format(full_filename))
        if (self.filename == full_filename) and self.force_change:
            self.property('filename').dispatch(self)
            # self.filename = ''
        self.filename = full_filename
        self.dismiss_popup()

    def cancel(self):
        self.dismiss_popup()


##############################################################################


class FileSaveDialog(FloatLayout):
    save = ObjectProperty(None)
    cancel = ObjectProperty(None)
    default_path = StringProperty(MFF_MUSCIMA_ROOT)

    # def on_key_down(self, window, key, scancode, codepoint, modifier):
    #     logging.info('FileSaveDialog: Captured down-key {0}/{1}/{2}'
    #                  ''.format(key, scancode, modifier))
    #     return True
    #
    # def on_key_up(self, window, key, scancode, *args, **kwargs):
    #     logging.info('FileSaveDialog: Captured up-key {0}/{1}'.format(key, scancode))
    #     return True


class FileSaver(FloatLayout):
    to_save = StringProperty()
    overwrite = BooleanProperty(False)
    text_input = StringProperty()

    last_output_path = StringProperty()

    def show_save(self, path=None):
        logging.info('Showing save with path {0}'.format(path))
        if path is not None:
            content = FileSaveDialog(save=self.save,
                                     cancel=self.dismiss_popup,
                                     default_path=path)
        else:
            content = FileSaveDialog(save=self.save,
                                     cancel=self.dismiss_popup)

        # Window.bind(on_key_down=content.on_key_down)
        # Window.bind(on_key_up=content.on_key_up)

        self._popup = Popup(title="Save file",
                            content=content,
                            size_hint=(0.5, 0.8))

        self._popup.open()

    def save(self, path, filename):
        output_path = os.path.join(path, filename)
        if os.path.isdir(output_path):
            logging.error('Export: Selected output is a directory! {0}'
                          ''.format(output_path))
            self.dismiss_popup()
        if os.path.isfile(output_path):
            if not self.overwrite:
                logging.error('Export: Selected output exists! {0}'
                              ''.format(output_path))
                self.dismiss_popup()
        with codecs.open(output_path, 'w', 'utf-8') as stream:
            stream.write(str(self.to_save))

        self.last_output_path = output_path
        self.dismiss_popup()

    def dismiss_popup(self):
        # Window.unbind(on_key_down=self._popup.content.on_key_down)
        # Window.unbind(on_key_up=self._popup.content.on_key_up)
        self._popup.dismiss()

    def cancel(self):
        self.dismiss_popup()


class OnBindFileSaver(FileSaver):
    """This FileSaver fakes the saving: it just fills in the filename
    property on the save() call and expects someone else binding to
    this property to do the actual saving."""
    filename = StringProperty(force_dispatch=True)

    def save(self, path, filename):
        output_path = os.path.join(path, filename)
        if os.path.isdir(output_path):
            logging.error('Export: Selected output is a directory! {0}'
                          ''.format(output_path))
            self.dismiss_popup()
        if os.path.isfile(output_path):
            if not self.overwrite:
                logging.error('Export: Selected output exists! {0}'
                              ''.format(output_path))
                self.dismiss_popup()

        # Leaves the saving for later.

        self.filename = output_path
        self.last_output_path = output_path
        self.dismiss_popup()

##############################################################################


class ConfirmationDialog(Popup):
    text = StringProperty('')

    ok_text = StringProperty('OK')
    cancel_text = StringProperty('Cancel')

    __events__ = ('on_ok', 'on_cancel')

    def ok(self):
        self.dispatch('on_ok')
        self.dismiss()

    def cancel(self):
        self.dispatch('on_cancel')
        self.dismiss()

    def on_ok(self):
        pass

    def on_cancel(self):
        pass


class MessageDialog(Popup):
    text = StringProperty('')
    title = StringProperty('Message')

    ok_text = StringProperty('OK')

    __events__ = ('on_ok',)

    def ok(self):
        self.dispatch('on_ok')
        self.dismiss()

    def on_ok(self):
        pass


##############################################################################

class InspectionPopup(Popup):
    source = StringProperty()

    def __init__(self, data_text, *args, **kwargs):
        super(InspectionPopup, self).__init__(*args, **kwargs)

        self.data_text = data_text
        self.image.texture.mag_filter = 'nearest'

    @property
    def image(self):
        return self.ids['inspected_image']

##############################################################################


def bbox_to_integer_bounds(ftop, fleft, fbottom, fright, to_integer=True):
    """Rounds off the CropObject bounds to the nearest integer
    so that no area is lost (e.g. bottom and right bounds are
    rounded up, top and left bounds are rounded down).

    Implementation
    --------------

    Calls the `CropObject` implementation of rounding off the bounding
    box, to avoid duplicity, as the MUSCIMarker implementation of CropObject
    representation of image annotations is used in the MUSCIMarker model.

    :param to_integer: If True, will return the bounds as `int`s. If False,
        will return `float`s.

    :returns: top, left, bottom, right (4-tuple).
    """
    t, l, b, r = CropObject.bbox_to_integer_bounds(ftop, fleft, fbottom, fright)
    if not to_integer:
        t, l, b, r = float(t), float(l), float(b), float(r)

    return t, l, b, r


def bbox_intersection(origin, intersect):
    """Returns the coordinates of the origin bounding box that
    are intersected by the intersect bounding box.

    >>> bounding_box = 10, 100, 30, 110
    >>> other_bbox = 20, 100, 40, 105
    >>> bbox_intersection(bounding_box, other_bbox)
    (10, 0, 20, 5)
    >>> bbox_intersection(other_bbox, bounding_box)
    (0, 0, 10, 5)
    >>> containing_bbox = 4, 55, 44, 115
    >>> bbox_intersection(bounding_box, containing_bbox)
    (0, 0, 20, 10)
    >>> contained_bbox = 12, 102, 22, 108
    >>> bbox_intersection(bounding_box, contained_bbox)
    (2, 2, 12, 8)
    >>> non_overlapping_bbox = 0, 0, 3, 3
    >>> bbox_intersection(bounding_box, non_overlapping_bbox) is None
    True

    """
    o_t, o_l, o_b, o_r = origin
    t, l, b, r = intersect

    out_top = max(t, o_t)
    out_left = max(l, o_l)
    out_bottom = min(b, o_b)
    out_right = min(r, o_r)

    if (out_top < out_bottom) and (out_left < out_right):
        return out_top - o_t, \
               out_left - o_l, \
               out_bottom - o_t, \
               out_right - o_l
    else:
        return None



def connected_components2bboxes(labels):
    """Returns a dictionary of bounding boxes (upper left c., lower right c.)
    for each label.

    >>> labels = [[0, 0, 1, 1], [2, 0, 0, 1], [2, 0, 0, 0], [0, 0, 3, 3]]
    >>> bboxes = connected_components2bboxes(labels)
    >>> bboxes[0]
    [0, 0, 4, 4]
    >>> bboxes[1]
    [0, 2, 2, 4]
    >>> bboxes[2]
    [1, 0, 3, 1]
    >>> bboxes[3]
    [3, 2, 4, 4]


    :param labels: The output of cv2.connectedComponents().

    :returns: A dict indexed by labels. The values are quadruplets
        (xmin, ymin, xmax, ymax) so that the component with the given label
        lies exactly within labels[xmin:xmax, ymin:ymax].
    """
    bboxes = {}
    for x, row in enumerate(labels):
        for y, l in enumerate(row):
            if l not in bboxes:
                bboxes[l] = [x, y, x+1, y+1]
            else:
                box = bboxes[l]
                if x < box[0]:
                    box[0] = x
                elif x + 1 > box[2]:
                    box[2] = x + 1
                if y < box[1]:
                    box[1] = y
                elif y + 1 > box[3]:
                    box[3] = y + 1
    return bboxes


def compute_connected_components(image):
    labels = skimage.measure.label(image, background=0)
    cc = int(labels.max())
    bboxes = connected_components2bboxes(labels)
    return cc, labels, bboxes


def image_mask_overlaps_cropobject(mask, cropobject,
                                   use_cropobject_mask=False):
    """Determines whether the given image mask overlaps the given CropObject.

    Can either take into account the cropobject's bounding box only, or can
    also take into account the cropobject's mask, according to the
    ``disregard_cropobject_mask`` flag.

    :param mask: A 2D numpy array, assumed to be a mask of the source image
        in which the CropObject was marked.

    :param cropobject: The cropobject for which we want to determine its
        mask.

    :param use_cropobject_mask: If False, will only check that the
        mask overlaps the CropObject's bounding box, not necessarily
        its mask.

    :return: True or False
    """
    t, l, b, r = cropobject.bounding_box
    mask_crop = mask[t:b, l:r]
    if (not use_cropobject_mask) or (cropobject.mask is None):
        return mask_crop.any() != 0
    else:
        return (mask_crop * cropobject.mask).any() != 0


def image_mask_overlaps_model_edge(mask, edge_start, edge_end, margin=2):
    """Determines whether the given image mask overlaps the given Edge.
    Assumes the EdgeView has been converted to model coordinates.


    """
    t = min(edge_start[0], edge_end[0])
    l = min(edge_start[1], edge_end[1])
    b = max(edge_start[0], edge_end[0]) + 1
    r = max(edge_start[1], edge_end[1]) + 1

    crop = mask[t:b, l:r]
    l = line(edge_start[0] - t, edge_start[1] - l,
             edge_end[0] - t, edge_end[1] - l)
    m2 = numpy.zeros(crop.shape)
    m2[l] = 1

    mc = crop * m2
    s = mc.sum()
    return s > 0

    # The edge passes through the middle of its bounding box!
    vert_mid, horz_mid = t + old_div((b - t), 2.0), l + old_div((r - l), 2.0)

    t_mid = max(0, int(floor(vert_mid) - margin))
    b_mid = min(int(ceil(vert_mid) + margin), mask.shape[0])
    l_mid = max(0, int(floor(horz_mid) - margin))
    r_mid = min(int(ceil(horz_mid) + margin), mask.shape[1])

    s = mask[t_mid:b_mid, l_mid:r_mid].sum()
    logging.warn('Middle: {0}:{1}, {2}:{3}'.format(t_mid, b_mid, l_mid, r_mid))
    return s > 0


##############################################################################

def filename2docname(filename):
    return os.path.splitext(os.path.basename(filename))[0]

##############################################################################


class ImageToModelScaler(Widget):
    """Use this class when you have an image inside a ScatterLayout
    and you need to convert coordinates from the Image widget to coordinates
    in the underlying image.

    If your widget coords are represented as (X, Y, height, width),
    use the cropobject_widget2model() method. If your widget coords
    are (top, left, bottom, right), use bbox_widget2model(). Note that
    in the second case, we expect top to be the widget-world top, so it
    will have a *larger* value than bottom. This second method can be used
    directly with the ('top', 'left', 'bottom', 'right') selection dictionary
    recorded by a BoundingBoxTracer.

    Note: when we say 'top', 'bottom', 'left' or 'right' in this context,
    we mean it in a WYSIWYG manner: the coordinate corresponding to the top
    boundary of the object you are seeing on the screen.

    If you need to map individual (X, Y) points: use point_widget2model
    and point_model2widget.

    """
    widget_height = NumericProperty(1.0)
    widget_width = NumericProperty(1.0)

    model_height = NumericProperty(1.0)
    model_width = NumericProperty(1.0)

    def __init__(self, image_widget, image_model, **kwargs):
        """Initialize the widget.

        :param image_widget: The Image widget. Expects coordinates to be
            bottom to top, left to right (counted from the bottom left corner).

        :param image_model: A numpy array of the actual image. Assumes
            shape[0] is height, shape[1] is width.
        """
        super(ImageToModelScaler, self).__init__(**kwargs)
        # logging.info('Scaler: image widget: {0}'.format(image_widget))
        # logging.info('Scaler: image widget parent: {0}'.format(image_widget.parent))
        # logging.info('Scaler: image widget pparent: {0}'.format(image_widget.parent.parent))
        self.reset(image_widget, image_model)

    def reset(self, image_widget, image_model):
        logging.info('Scaler: RESET')
        # Bind widget shape changes to our properties.
        image_widget.bind(height=self.set_widget_height)
        image_widget.bind(width=self.set_widget_width)
        self.widget_height = image_widget.height
        self.widget_width = image_widget.width
        logging.info('Scaler: Widget image shape: {0}'.format((self.widget_height,
                                                       self.widget_width)))

        model_shape = image_model.shape
        self.model_height = model_shape[0]
        self.model_width = model_shape[1]
        logging.info('Scaler: Model image shape: {0}'.format(model_shape))
        logging.info('Scaler: m2w ratios: {0}'.format((self.m2w_ratio_height,
                                               self.m2w_ratio_width)))
        logging.info('Scaler: w2m ratios: {0}'.format((self.w2m_ratio_height,
                                               self.w2m_ratio_width)))

    def cropobject_widget2model(self, wX, wY, wHeight, wWidth):
        raise NotImplementedError()

    def cropobject_model2widget(self, mX, wY, mHeight, mWidth):
        raise NotImplementedError()

    def bbox_widget2model(self, wTop, wLeft, wBottom, wRight):
        mTop = (self.widget_height - wTop) * self.w2m_ratio_height
        mBottom = (self.widget_height - wBottom) * self.w2m_ratio_height
        mLeft = wLeft * self.w2m_ratio_width
        mRight = wRight * self.w2m_ratio_width
        logging.info('Scaler: From widget: {0} to model: {1}. w2m ratios: {2}'
                     ''.format((wTop, wLeft, wBottom, wRight),
                               (mTop, mLeft, mBottom, mRight),
                               (self.w2m_ratio_height, self.w2m_ratio_width)))
        return mTop, mLeft, mBottom, mRight

    def bbox_model2widget(self, mTop, mLeft, mBottom, mRight):
        wTop = self.widget_height - (mTop * self.m2w_ratio_height)
        wBottom = self.widget_height - (mBottom * self.m2w_ratio_height)
        wLeft = mLeft * self.m2w_ratio_width
        wRight = mRight * self.m2w_ratio_width
        return wTop, wLeft, wBottom, wRight

    def point_widget2model(self, wX, wY):
        """Maps a point from the widget (kivy) space to the model (numpy) space.

        :param wX: horizontal coordinate

        :param wY: vertical coordinate

        :returns: A tuple (mX, mY), where mX is the model *vertical* coordinate
            (row) and mY is the model *horizontal* coordinate (column).
        """
        mX = (self.widget_height - wY) * self.w2m_ratio_height
        mY = wX * self.w2m_ratio_width
        return mX, mY

    def point_model2widget(self, mX, mY):
        """Maps a point from the widget (kivy) space to the model (numpy) space.

        :param mX: horizontal coordinate

        :param mY: vertical coordinate

        :returns: A tuple (wX, wY), where wX is the widget *horizontal* coordinate
            (column) and wY is the model *vertical* coordinate (row), measured
            from the *bottom*.
        """
        raise NotImplementedError()

    ###################################
    # Listening to widget size changes.

    def set_widget_height(self, instance, pos):
        logging.info('Scaler: widget height change triggered, pos={0}'.format(pos))
        self.widget_height = pos

    def set_widget_width(self, instance, pos):
        logging.info('Scaler: widget width change triggered, pos={0}'.format(pos))
        self.widget_width = pos

    ####################################
    # Scaling ratios.
    # "m2w" is "multiply by this ratio when converting from Model to Widget".
    # "w2m" is "multiply by this ratio when converting from Widget to Model".
    @property
    def m2w_ratio_height(self):
        return self.widget_height * 1.0 / self.model_height

    @property
    def m2w_ratio_width(self):
        return self.widget_width * 1.0 / self.model_width

    @property
    def w2m_ratio_height(self):
        return self.model_height * 1.0 / self.widget_height

    @property
    def w2m_ratio_width(self):
        return self.model_width * 1.0 / self.widget_width
