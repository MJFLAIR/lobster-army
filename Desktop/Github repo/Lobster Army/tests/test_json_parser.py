import unittest

from llm.json_parser import safe_parse_json, JSONParseError

class TestJSONParser(unittest.TestCase):

    def test_pure_json(self):
        text = '{"name": "lobster", "count": 5}'
        result = safe_parse_json(text)
        self.assertEqual(result, {"name": "lobster", "count": 5})

    def test_markdown_json_block(self):
        text = '''Here is your JSON:
```json
{
  "status": "ok"
}
```
'''
        result = safe_parse_json(text)
        self.assertEqual(result, {"status": "ok"})

    def test_plain_markdown_block(self):
        text = '''
```
[
  {"id": 1},
  {"id": 2}
]
```'''
        result = safe_parse_json(text)
        self.assertEqual(result, [{"id": 1}, {"id": 2}])

    def test_fallback_object(self):
        text = 'The result is {"nested": {"value": 123}}.'
        result = safe_parse_json(text)
        self.assertEqual(result, {"nested": {"value": 123}})

    def test_fallback_list(self):
        text = 'Results: [{"a": 1}, {"b": 2}]'
        result = safe_parse_json(text)
        self.assertEqual(result, [{"a": 1}, {"b": 2}])

    def test_parse_error(self):
        text = 'No JSON here!'
        with self.assertRaises(JSONParseError):
            safe_parse_json(text)

if __name__ == "__main__":
    unittest.main()
