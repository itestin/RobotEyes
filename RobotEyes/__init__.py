# -*-coding:utf-8 -*-
from datetime import datetime
import shutil
import time
from threading import Thread

from PIL import Image
from robot.libraries.BuiltIn import BuiltIn

from .constants import *
from .report_utils import *
from .imagemagick import Imagemagick
from .selenium_hooks import SeleniumHooks
from .report_generator import generate_report
from .opencv_match import UIMatcher
from . import Log

class RobotEyes(object):
    output_dir = ''
    images_base_folder = ''
    test_name = ''
    test_name_folder = ''
    baseline_dir = ''
    browser = None
    ROBOT_LISTENER_API_VERSION = ROBOT_LISTENER_API_VERSION
    ROBOT_LIBRARY_SCOPE = ROBOT_LIBRARY_SCOPE
    fail = False
    cleanup_files = None
    pass_color = 'green'
    fail_color = 'red'

    # Keeping this arg to avoid exceptions for those who have added tolerance in the previous versions.
    def __init__(self, tolerance=0):
        self.ROBOT_LIBRARY_LISTENER = self
        self.lib = 'none'

    def open_eyes(self, lib='SeleniumLibrary', tolerance=0, template_id='', cleanup=None):
        self._set_cleanup(cleanup)
        self.tolerance = float(tolerance)
        self.tolerance = self.tolerance / 100 if self.tolerance >= 1 else self.tolerance
        self.stats = {}
        self.fail = False
        self.baseline_dir = self._get_baseline_dir()
        self.actual_dir = self._get_actual_dir()
        self.output_dir = self._output_dir()
        self.lib = lib
        self.images_base_folder = os.path.join(self.output_dir, IMAGES_FOLDER)
        if lib.lower() != 'none':
            self.browser = SeleniumHooks(lib)
        self.test_name = BuiltIn().replace_variables('${TEST NAME}')
        if template_id:
            self.test_name += '_%s' % template_id
        self.test_name_folder = self.test_name.replace(' ', '_')
        print("roboteyestestfolder: %s" % self.test_name_folder)
        # delete if directory already exist. Fresh test
        self._delete_folder_if_exists()
        # recreate deleted folder
        self._create_empty_folder()
        self.count = 1

    # Captures full screen
    # def capture_full_screen(self, tolerance=None, blur=[], radius=50, name=None, redact=[]):
    #     tolerance = float(tolerance) if tolerance else self.tolerance
    #     tolerance = tolerance/100 if tolerance >= 1 else tolerance
    #     name = self._get_name() if name is None else name
    #     name += '.png'
    #     path = os.path.join(self.path, name)
    #     self.browser.capture_full_screen(path, blur, radius, redact)
    #     self._fix_base_image_size(path, name)
    #     self.stats[name] = tolerance
    #     self.count += 1

    # Captures a specific region in a mobile screen
    # def capture_mobile_element(self, selector, tolerance=None, blur=[], radius=50, name=None, redact=[]):
    #     tolerance = float(tolerance) if tolerance else self.tolerance
    #     name = self._get_name() if name is None else name
    #     name += '.png'
    #     path = os.path.join(self.path, name)
    #     self.browser.capture_mobile_element(selector, path, blur, radius, redact)
    #     self.stats[name] = tolerance
    #     self.count += 1

    # # Captures a specific region in a webpage
    # def capture_element(self, selector, tolerance=None, blur=[], radius=50, name=None, redact=[]):
    #     tolerance = float(tolerance) if tolerance else self.tolerance
    #     tolerance = tolerance/100 if tolerance >= 1 else tolerance
    #     name = self._get_name() if name is None else name
    #     name += '.png'
    #     path = os.path.join(self.path, name)
    #     time.sleep(1)
    #     self.browser.capture_element(path, selector, blur, radius, redact)
    #     self._fix_base_image_size(path, name)
    #     self.stats[name] = tolerance
    #     self.count += 1

    def scroll_to_element(self, selector):
        self.browser.scroll_to_element(selector)

    def element_image_compare(self, selector, template_path, diff_allow_value=4, retry=2):
        """Compare template image with element.

        selector: element locator

        template_path: xxxx.png

        diff_allow_value: <0 number

        retry: 1~10 number

        Examples:
        | Element Image Compare | locator | template_image | diff_allow_value |  retry | diff_allow_value default is 4, retry default is 2
        """
        tolerance = 0
        trimmed, diff_result = self.browser.element_image_compare(selector, template_path, self.baseline_dir,
                                                                          diff_allow_value, retry)
        color, result = self._get_result(trimmed, tolerance)
        if color != self.pass_color:
            BuiltIn().run_keyword('Capture Page Screenshot') if self.fail else ''
            BuiltIn().run_keyword('Fail',
                                  f'Compare element image failed , difference value {diff_result}, result: {result}') if self.fail else ''

    def image_is_in_screen(self, template_path, match_points=4, retry=2):
        """Assert template image is in screen.

        template_path: xxxx.png

        match_points: 1~100 number

        retry: 1~10 number

        Examples:
        | Image Is In Screen | template_image | match_points |  retry | match_points default is 4, retry default is 2
        """
        tolerance = 0
        trimmed, _, match_points_length = self.browser.image_is_in_screen(template_path, self.baseline_dir, match_points, retry)
        color, result = self._get_result(trimmed, tolerance)
        if color != self.pass_color:
            BuiltIn().run_keyword('Capture Page Screenshot') if self.fail else ''
            BuiltIn().run_keyword('Fail', f'Image is not in screen , match points {match_points_length},  result: {result}') if self.fail else ''

    def click_by_image(self, template_path, match_points=8, retry=2):
        """click template image in screen.

        template_path: xxxx.png

        match_points: 1~100 number

        retry: 1~10 number

        Examples:
        | Click By Image | template_image | match_points |  retry | match_points default is 4, retry default is 2
        """
        tolerance = 0
        trimmed, loc, match_points_length = self.browser.image_is_in_screen(template_path, self.baseline_dir, match_points, retry)
        failed = 0
        if trimmed or not loc:
            failed = 1
        self.browser.click_locxy(loc[0], loc[1])
        color, result = self._get_result(failed, tolerance)
        if color != self.pass_color:
            BuiltIn().run_keyword('Capture Page Screenshot') if self.fail else ''
            BuiltIn().run_keyword('Fail', f'Image is not in screen , match points {match_points_length},  result: {result}') if self.fail else ''

    def compare_two_images(self, ref, actual, output, tolerance=None):
        ref += '.png' if ref.split('.')[-1] not in IMAGE_EXTENSIONS else ''
        actual += '.png' if actual.split('.')[-1] not in IMAGE_EXTENSIONS else ''
        output += '.png' if output.split('.')[-1] not in IMAGE_EXTENSIONS else ''
        tolerance = float(tolerance) if tolerance else self.tolerance
        tolerance = tolerance / 100 if tolerance >= 1 else tolerance

        if not ref or not actual:
            raise Exception('Please provide reference and actual image names')

        first_path = os.path.join(self.baseline_dir, ref)
        second_path = os.path.join(self.actual_dir, actual)

        if os.path.exists(first_path) and os.path.exists(second_path):
            diff_path = os.path.join(self.path, output)
            difference = Imagemagick(first_path, second_path, diff_path).compare_images()
            color, result = self._get_result(difference, tolerance)
            self.stats[output] = tolerance
            text = '%s %s' % (result, color)
            txt_path = os.path.join(self.path, output + '.txt')
            outfile = open(txt_path, 'w')
            outfile.write(text)
            outfile.write("\n")
            img_names = '%s %s' % (ref, actual)
            outfile.write(img_names)
            outfile.close()
            if color == self.pass_color and self.cleanup_files is not None:
                self._cleanup_passed(self.actual_dir, diff_path)
        else:
            raise Exception('Image %s or %s doesnt exist' % (ref, actual))

    def compare_images(self):
        test_name = self.test_name.replace(' ', '_')
        baseline_path = os.path.join(self.baseline_dir, test_name)
        actual_path = os.path.join(self.images_base_folder, ACTUAL_IMAGE_BASE_FOLDER, test_name)
        diff_path = os.path.join(self.images_base_folder, DIFF_IMAGE_BASE_FOLDER, test_name)

        if not os.path.exists(diff_path):
            os.makedirs(diff_path)

        # compare actual and baseline images and save the diff image
        for filename in os.listdir(actual_path):
            if filename.endswith('.png'):
                b_path = os.path.join(baseline_path, filename)
                a_path = os.path.join(actual_path, filename)
                d_path = os.path.join(diff_path, filename)
                txt_path = os.path.join(actual_path, filename + '.txt')

                if os.path.exists(b_path):
                    difference = Imagemagick(b_path, a_path, d_path).compare_images()

                    try:
                        threshold = float(self.stats[filename])
                    except ValueError:
                        raise Exception('Invalid tolerance: %s' % self.stats[filename])

                    color, result = self._get_result(difference, threshold)
                    text = '%s %s' % (result, color)
                else:
                    shutil.copy(a_path, b_path)
                    color = self.pass_color
                    text = '%s %s' % ('None', color)

                output = open(txt_path, 'w')
                output.write(text)
                output.close()
                if color == self.pass_color and self.cleanup_files is not None:
                    self._cleanup_passed(actual_path, diff_path)
        BuiltIn().run_keyword('Fail', 'Image dissimilarity exceeds tolerance') if self.fail else ''

    def _set_cleanup(self, cleanup):
        cleanup_options = [None, 'all_passed', 'diffs_passed', 'actuals_passed']
        self.cleanup_files = None
        if cleanup in cleanup_options:
            self.cleanup_files = cleanup

    def _delete_folder_if_exists(self):
        actual_image_test_folder = os.path.join(self.images_base_folder, ACTUAL_IMAGE_BASE_FOLDER, self.test_name_folder)
        diff_image_test_folder = os.path.join(self.images_base_folder, DIFF_IMAGE_BASE_FOLDER, self.test_name_folder)

        if os.path.exists(actual_image_test_folder):
            shutil.rmtree(actual_image_test_folder)

        if os.path.exists(diff_image_test_folder):
            shutil.rmtree(diff_image_test_folder)

    def _create_empty_folder(self):
        if self.lib.lower() != 'none':
            self.path = os.path.join(self.baseline_dir, self.test_name_folder)

            if not os.path.exists(self.path):
                os.makedirs(self.path)

        self.path = os.path.join(self.images_base_folder, ACTUAL_IMAGE_BASE_FOLDER, self.test_name_folder)

        if not os.path.exists(self.path):
            os.makedirs(self.path)

    def _resize(self, *args):
        for arg in args:
            img = Image.open(arg)
            img = img.resize((1024, 700), Image.ANTIALIAS)
            img.save(arg)

    def _fix_base_image_size(self, path, image_name):
        test_name = self.test_name.replace(' ', '_')
        base_image = os.path.join(self.baseline_dir, test_name, image_name)
        if os.path.exists(base_image):
            im = Image.open(path)
            width, height = im.size
            im.close()

            im = Image.open(base_image)
            b_width, b_height = im.size
            if width != b_width or height != b_height:
                im = im.resize((width, height), Image.ANTIALIAS)
                im.save(base_image)

    def _delete_report_if_old(self, path):
        t1 = datetime.fromtimestamp(os.path.getmtime(path))
        t2 = datetime.now()
        diff = (t2 - t1).seconds
        os.remove(path) if diff > REPORT_EXPIRATION_THRESHOLD else ''

    def _output_dir(self):
        output_dir = BuiltIn().replace_variables('${OUTPUT DIR}')

        if 'pabot_results' in output_dir:
            index = output_dir.find(os.path.sep + 'pabot_results')
            return output_dir[:index]
        return output_dir

    def _get_result(self, difference, threshold):
        difference, threshold = int(difference*100), int(threshold*100)
        if difference > threshold:
            color = self.fail_color
            result = '%s<%s' % (threshold, difference)
            self.fail = True
        elif difference == threshold:
            color = self.pass_color
            result = '%s==%s' % (threshold, difference)
        else:
            color = self.pass_color
            result = '%s>%s' % (threshold, difference)
        return color, result

    def _get_baseline_dir(self):
        baseline_dir = BuiltIn().get_variable_value('${images_dir}')
        if not baseline_dir:
            BuiltIn().run_keyword('Fail', 'Please provide image baseline directory. Ex: -v images_dir:base')

        os.makedirs(baseline_dir) if not os.path.exists(baseline_dir) else ''
        return baseline_dir

    def _get_actual_dir(self):
        return BuiltIn().get_variable_value('${actual_dir}')

    def _get_name(self):
        return 'img%s' % str(self.count)

    def _cleanup_passed(self, actuals_path, diff_path):
        if self.cleanup_files == 'diffs_passed':
            self._cleanup_passed_files([diff_path])
        elif self.cleanup_files == 'actuals_passed':
            self._cleanup_passed_files([actuals_path])
        else:
            self._delete_folder_if_exists()

    @staticmethod
    def _cleanup_passed_files(test_paths):
        for test_path in test_paths:
            if os.path.exists(test_path):
                shutil.rmtree(test_path)

    def _end_test(self, data, test):
        if hasattr(self, 'lib') and self.lib.lower() == 'none':
            if self.fail:
                test.status = 'FAIL'
                test.message = 'Image dissimilarity exceeds tolerance'

    def _close(self):
        if self.baseline_dir and self.output_dir:
            thread = Thread(
                target=generate_report,
                args=(self.baseline_dir, self.output_dir, self.actual_dir,)
            )
            thread.start()
