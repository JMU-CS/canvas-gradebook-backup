#!/home/stewarmc/canvasapi-venv/bin/python

import argparse
from canvasapi import Canvas
import os
import sys
from datetime import datetime
import csv

"""
Given a Canvas course id (and optionally a single assignment id), create a csv file that stores the current scores for all students for all assignments (that have the matching assignment id if it was provided). 
This csv file should be formatted such that it could be imported into Canvas to restore the scores.
"""


canvas = None
canvas_student_data = {}
course_student_id_to_sis_id = {}
sis_id_to_course_student_id = {}

CANVAS_REQUIRED_FIELDS = [
    "Student",
    "ID",
    "SIS User ID",
    "SIS Login ID",
    "Section",
]


def main(canvas_url, canvas_key, course, assignment=None, outfile=None):
    print(canvas_url, canvas_key)
    global canvas
    canvas = Canvas(canvas_url, canvas_key)
    the_course = canvas.get_course(course)
    course_students = [s for s in the_course.get_recent_students()]
    global course_student_id_to_sis_id
    course_student_id_to_sis_id = {s.id: s.sis_user_id for s in course_students}
    global sis_id_to_course_student_id
    sis_id_to_course_student_id = {s.sis_user_id: s.id for s in course_students}
    global canvas_student_data
    for section in the_course.get_sections():
        for student in section.get_enrollments():
            if student.type == "StudentEnrollment":
                student_info = [
                    student.user["sortable_name"],
                    sis_id_to_course_student_id[student.sis_user_id],
                    student.sis_user_id,
                    student.user["login_id"],
                    section.name,
                ]
                canvas_student_data[student.sis_user_id] = {
                    CANVAS_REQUIRED_FIELDS[i]: student_info[i]
                    for i in range(len(CANVAS_REQUIRED_FIELDS))
                }
    if assignment is not None:
        the_assignment = the_course.get_assignment(assignment)
        data = backup_single_assignment(the_course, the_assignment)
        backup_path = filename(the_course, the_assignment, outfile=outfile)
        write_backup(backup_path, data)
    else:
        # must be that args.all is True
        data = backup_all_assignments(the_course)
        merged = merge(data)
        backup_path = filename(the_course, all=True, outfile=outfile)
        write_backup(backup_path, merged)


def backup_all_assignments(the_course):
    all_assns = [s for s in the_course.get_assignments()]
    results = {}
    # for i in range(5):
    # a = all_assns[i]
    for a in all_assns:
        results[f"{a.name} ({a.id})"] = backup_single_assignment(the_course, a)
    return results


def merge(data):
    merged = {}
    for single_assn_scores in data.values():
        for v in single_assn_scores:
            if v["SIS User ID"] not in merged:
                merged[v["SIS User ID"]] = {}
            merged[v["SIS User ID"]] |= v
    return merged


def backup_single_assignment(the_course, the_assignment):
    all = [s for s in the_assignment.get_submissions()]

    subs = []
    for s in all:
        if s.user_id not in course_student_id_to_sis_id:
            missing_student = the_course.get_user(s.user_id)
            if missing_student.short_name != "Test Student":
                print(f"{s.user_id} not in {course_student_id_to_sis_id.keys()}")
                print(f"for submission {s.id}")
                print(f"for assignment {the_assignment.id}")
                sys.exit(1)
        else:
            sis_id = course_student_id_to_sis_id[s.user_id]
            if sis_id not in canvas_student_data:
                print(f"{sis_id} not in {canvas_student_data.keys()}")
                sys.exit(1)

            score = ""
            if not s.missing:
                score = s.score
            student_values = canvas_student_data[sis_id] | {
                f"{the_assignment.name} ({the_assignment.id})": score
            }
            subs.append(student_values)
    return sorted(subs, key=lambda x: x["Student"])


def write_backup(filename, data):
    # FIXME: this next line breaks the single assignment backup
    fields = [v for v in data.values()][0].keys()

    with open(filename, "w") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data.values())


def filename(course, assignment=None, all=None, outfile=None):
    # TODO: consider checking if this is a directory in which case naming the file according to the logic in this function
    if outfile is not None and not os.path.isdir(outfile):
        return outfile
    directory = ""
    if os.path.isdir(outfile):
        directory = outfile
    ts = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    if all is not None:
        return os.path.join(directory, f"{ts}-{course.id}-ALL.bk.csv")
    else:
        return os.path.join(
            directory,
            f"{ts}-{course.id}-{assignment.name.replace(' ', '_')}.bk.csv",
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--canvas_key",
        default=None,
        help="your canvas account token. see: \
            https://canvas.instructure.com/doc/api/file.oauth.html#manual-token-generation",
    )

    parser.add_argument(
        "--canvas_url",
        default=None,
        help="the URL of your canvas instance, e.g. https://canvas.jmu.edu/",
    )

    parser.add_argument("course", help="canvas course id")

    # TODO: consider making it possible to write to stdout to support scripty pipey funtimes
    parser.add_argument("-o", "--outfile", help="file to write the backup to")

    parser.add_argument("--assignment", help="canvas assignment id", required=False)

    parser.add_argument(
        "--all", action="store_true", help="backup the scores for all assignments"
    )

    args = parser.parse_args()

    canvas_key = args.canvas_key
    canvas_url = args.canvas_url
    if canvas_key is None:
        canvas_key = os.environ["CANVAS_KEY"]
    if canvas_url is None:
        canvas_url = os.environ["CANVAS_URL"]
    if canvas_key is None or canvas_url is None:
        print(
            "must provide canvas api key and url via either the optional \
            flags or the environment variables: CANVAS_KEY and CANVAS_URL"
        )
        sys.exit(1)

    if args.assignment is None and not args.all:
        print("must provide either an assignment id or the --all flag")
        sys.exit(1)

    # ambiguous intent
    if args.all and args.assignment is not None:
        print("cannot provide both an assignment id and the --all flag")
        sys.exit(1)
    main(canvas_url, canvas_key, args.course, args.assignment, args.outfile)
