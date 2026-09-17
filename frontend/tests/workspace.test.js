import test from 'node:test';
import assert from 'node:assert/strict';
import {pythonTokens} from '../src/features/strategy-lab/workspace-utils.js';

test('Python highlighting preserves exact source including comments, quotes and HTML',()=>{
  const source='def test():\n    # comment\n    x = "<script>alert(1)</script>"\n    return 2.5\n';
  const tokens=pythonTokens(source);
  assert.equal(tokens.map(t=>t.text).join(''),source);
  assert.ok(tokens.some(t=>t.kind==='keyword'&&t.text==='def'));
  assert.ok(tokens.some(t=>t.kind==='comment'));
  assert.ok(tokens.some(t=>t.kind==='string'&&t.text.includes('<script>')));
});
test('Multiline and incomplete strings preserve edits without executing anything',()=>{
  for(const source of ['', 'x = """line\nreturn\n"""', "x = '''unfinished\nclass <&>"])
    assert.equal(pythonTokens(source).map(t=>t.text).join(''),source);
});
