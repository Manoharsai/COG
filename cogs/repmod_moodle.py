# -*- coding: utf-8 -*-

# Andy Sayler
# Summer 2014
# Univerity of Colorado


import time
import logging

import moodle.ws

import config

import repmod


EXTRA_REPORTER_SCHEMA = ['moodle_asn_id', 'moodle_respect_duedate', 'moodle_only_higher',
                         'moodle_prereq_id', 'moodle_prereq_min']
EXTRA_REPORTER_DEFAULTS = {'moodle_respect_duedate': "1", 'moodle_only_higher': "1",
                           'moodle_prereq_id': "0", 'moodle_prereq_min': "0"}

_MAX_COMMENT_LEN = 2000
_FLOAT_MARGIN = 0.01

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())


class MoodleReporterError(repmod.ReporterError):
    """Base class for Moodle Reporter Exceptions"""

    def __init__(self, *args, **kwargs):

        # Call Parent
        super(MoodleReporterError, self).__init__(*args, **kwargs)


class Reporter(repmod.Reporter):

    def __init__(self, rpt, run):

        # Call Parent
        super(Reporter, self).__init__(rpt, run)
        msg = "repmod_moodle: Initializing reporter {:s}".format(rpt)
        logger.info(self._format_msg(msg))

        # Check Input
        if rpt['mod'] != 'moodle':
            msg = "repmod_moodle: Requires reporter with repmod 'moodle'"
            logger.error(self._format_msg(msg))
            raise MoodleReporterError(msg)

        # Save vars
        self.asn_id = rpt['moodle_asn_id']

        # Setup Vars
        self.host = config.REPMOD_MOODLE_HOST

        # Setup WS
        self.ws = moodle.ws.WS(self.host)
        try:
            self.ws.authenticate(config.REPMOD_MOODLE_USERNAME,
                                 config.REPMOD_MOODLE_PASSWORD,
                                 config.REPMOD_MOODLE_SERVICE,
                                 error=True)
        except Exception as e:
            msg = "repmod_moodle: authenticate failed: {:s}".format(e)
            logger.error(self._format_msg(msg))
            raise

    def get_grade(self, asn_id, usr_id):

        assignments = self.ws.mod_assign_get_grades([asn_id])["assignments"]
        if assignments:
            assignment = assignments.pop()
            grades = assignment['grades']
            grades_by_uid = {}
            for grade in grades:
                uid = int(grade["userid"])
                if uid in grades_by_uid:
                    grades_by_uid[uid].append(grade)
                else:
                    grades_by_uid[uid] = [grade]
            if usr_id in grades_by_uid:
                last_grade = -1.0
                last_num = None
                for attempt in grades_by_uid[usr_id]:
                    num = int(attempt['attemptnumber'])
                    if num > last_num:
                        last_num = num
                        last_grade = float(attempt['grade'])
                return last_grade
            else:
                return None
        else:
            raise ValueError("No assignment {} grades found".format(asn_id))

    def file_report(self, usr, grade, comment):

        # Call Parent
        super(Reporter, self).file_report(usr, grade, comment)
        msg = "repmod_moodle: Filing report for user {:s}".format(usr)
        logger.info(self._format_msg(msg))

        # Check Moodle User
        if usr['auth'] != 'moodle':
            msg = "repmod_moodle: Requires user with authmod 'moodle'"
            logger.error(self._format_msg(msg))
            raise MoodleReporterError(msg)

        # Extract Vars
        asn_id = int(self.asn_id)
        usr_id = int(usr['moodle_id'])
        grade = float(grade)

        # Check Due Date
        if 'moodle_respect_duedate' in self._rpt and self._rpt['moodle_respect_duedate']:
            respect_duedate = bool(int(self._rpt['moodle_respect_duedate']))
        else:
            respect_duedate = bool(int(EXTRA_REPORTER_DEFAULTS['moodle_respect_duedate']))
        if respect_duedate:
            time_due = None
            courses = self.ws.mod_assign_get_assignments([])["courses"]
            for course in courses:
                assignments = course["assignments"]
                for assignment in assignments:
                    if (int(assignment["id"]) == int(asn_id)):
                        time_due = float(assignment["duedate"])
                    if time_due is not None:
                        break
                if time_due is not None:
                    break
            if time_due is None:
                msg = "repmod_moodle: Could not find assignment {:d}".format(asn_id)
                logger.error(self._format_msg(msg))
                raise MoodleReporterError(msg)
            if time_due > 0:
                time_now = time.time()
                if (time_now > time_due):
                    time_now_str = time.strftime("%d/%m/%y %H:%M:%S %Z", time.localtime(time_now))
                    time_due_str = time.strftime("%d/%m/%y %H:%M:%S %Z", time.localtime(time_due))
                    msg = "repmod_moodle: "
                    msg += "Current time ({:s}) ".format(time_now_str)
                    msg += "is past due date ({:s}): ".format(time_due_str)
                    msg += "No grade written to Moodle"
                    logger.warning(self._format_msg(msg))
                    raise MoodleReporterError(msg)

        # Check if grade is higher than prereq min
        if 'moodle_prereq_id' in self._rpt and self._rpt['moodle_prereq_id']:
            prereq_id = int(self._rpt['moodle_prereq_id'])
        else:
            prereq_id = int(EXTRA_REPORTER_DEFAULTS['moodle_prereq_id'])
        if 'moodle_prereq_min' in self._rpt and self._rpt['moodle_prereq_min']:
            prereq_min = float(self._rpt['moodle_prereq_min'])
        else:
            prereq_min = int(EXTRA_REPORTER_DEFAULTS['moodle_prereq_min'])
        if prereq_id and prereq_min:
            try:
                prereq_grade = self.get_grade(prereq_id, usr_id)
            except ValueError as err:
                msg = "repmod_moodle: Could not find prereq assignment {:d}".format(prereq_id)
                logger.error(self._format_msg(msg))
                raise MoodleReporterError(msg)
            if prereq_grade is None:
                msg = "repmod_moodle: "
                msg += "No Assignment {} grade found.".format(prereq_id)
                msg += "You must complete that asssgnment before being graded on this one: "
                msg += "No grade written to Moodle"
                logger.warning(self._format_msg(msg))
                raise MoodleReporterError(msg)
            elif prereq_grade < prereq_min:
                msg = "repmod_moodle: "
                msg += "Assignment {} grade ({:.2f}) ".format(prereq_id, last_grade)
                msg += "is lower than required grade ({:.2f}): ".format(prereq_min)
                msg += "No grade written to Moodle"
                logger.warning(self._format_msg(msg))
                raise MoodleReporterError(msg)

        # Check is grade is higher than current
        if 'moodle_only_higher' in self._rpt and self._rpt['moodle_only_higher']:
            only_higher = bool(int(self._rpt['moodle_only_higher']))
        else:
            only_higher = bool(int(EXTRA_REPORTER_DEFAULTS['moodle_only_higher']))
        if only_higher:
            prev_grade = self.get_grade(asn_id, usr_id)
            if prev_grade is None:
                pass
            elif grade < prev_grade:
                msg = "repmod_moodle: "
                msg += "Previous grade ({:.2f}) ".format(float(last_grade))
                msg += "is greater than current grade ({:.2f}): ".format(float(grade))
                msg += "No grade written to Moodle"
                logger.warning(self._format_msg(msg))
                raise MoodleReporterError(msg)

        # Limit Output
        warning = "\nWARNING: Output Truncated"
        max_len = (_MAX_COMMENT_LEN - len(warning))
        if len(comment) > max_len:
            comment = comment[:max_len]
            comment += warning

        # Log Grade
        try:
            self.ws.mod_assign_save_grade(asn_id, usr_id, grade, comment=comment)
        except Exception as e:
            msg = "repmod_moodle: mod_assign_save_grade failed: {:s}".format(e)
            logger.error(self._format_msg(msg))
            raise
