// Display-only tokenizer. Tokens are rendered as React text, never as HTML.
export function pythonTokens(source) {
  const pattern = /#[^\n]*|"""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|\b(?:class|def|return|if|elif|else|for|while|in|import|from|as|with|try|except|finally|raise|assert|pass|None|True|False|and|or|not|lambda|yield|async|await)\b|\b\d+(?:\.\d+)?\b/g;
  let offset=0; const tokens=[];
  for (const match of source.matchAll(pattern)) {
    if (match.index > offset) tokens.push({text:source.slice(offset,match.index),kind:'plain'});
    const text=match[0];
    tokens.push({text,kind:text.startsWith('#')?'comment':/^["']/.test(text)?'string':/^\d/.test(text)?'number':'keyword'});
    offset=match.index+text.length;
  }
  if (offset<source.length) tokens.push({text:source.slice(offset),kind:'plain'});
  return tokens;
}
