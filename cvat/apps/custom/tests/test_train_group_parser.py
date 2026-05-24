from django.test import SimpleTestCase

from cvat.apps.custom.train_group_parser import ParsedRow, ValidationError


class DataClassesTest(SimpleTestCase):
    def test_parsed_row_holds_train_id_and_group(self):
        row = ParsedRow(train_id="3101F", group="A", line_no=2)
        self.assertEqual(row.train_id, "3101F")
        self.assertEqual(row.group, "A")
        self.assertEqual(row.line_no, 2)

    def test_validation_error_holds_line_train_id_reason(self):
        err = ValidationError(line=14, train_id="3101 F", reason="whitespace not allowed")
        self.assertEqual(err.line, 14)
        self.assertEqual(err.reason, "whitespace not allowed")
