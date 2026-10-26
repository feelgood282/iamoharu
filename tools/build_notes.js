#!/usr/bin/env node
/* 결 고운 하루 노트: 메인 노트 목록의 정적 마크업 만들기
   index.html 스크립트의 CATS·NOTES·notesHTML()로 '전체' 탭 화면을 그려
   <div id="noteList">…</div><!--/noteList--> 안에 그대로 넣는다.
   (검색 로봇이 자바스크립트 없이도 카드를 읽고, 첫 화면이 덜컹거리지 않게 하기 위함)

   새 노트를 NOTES 배열 맨 위에 추가한 뒤 한 번 실행:
       node tools/build_notes.js
*/
const fs = require('fs');
const path = require('path');

const file = path.join(__dirname, '..', 'index.html');
let html = fs.readFileSync(file, 'utf8');

const pick = (re, name) => {
  const m = html.match(re);
  if (!m) { console.error(`index.html에서 ${name}을(를) 찾지 못했습니다.`); process.exit(1); }
  return m[0];
};
const cats = pick(/const CATS = \[[\s\S]*?\];/, 'CATS');
const notes = pick(/const NOTES = \[[\s\S]*?\n\];/, 'NOTES');
const render = pick(/\/\*render:start\*\/[\s\S]*?\/\*render:end\*\//, 'notesHTML');

const markup = new Function(`${cats}\n${notes}\n${render}\nreturn notesHTML('전체');`)();

const START = '<div id="noteList">';
const END = '</div><!--/noteList-->';
const a = html.indexOf(START), b = html.indexOf(END, a);
if (a < 0 || b < 0) { console.error('noteList 자리를 찾지 못했습니다.'); process.exit(1); }
html = html.slice(0, a + START.length) + markup + html.slice(b);
fs.writeFileSync(file, html);

const count = (markup.match(/<article/g) || []).length;
console.log(`정적 노트 카드 ${count}장을 index.html에 넣었습니다.`);
