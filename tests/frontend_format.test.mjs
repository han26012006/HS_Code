import test from 'node:test';
import assert from 'node:assert/strict';
import {formatDate,formatTime,todayVN} from '../frontend/src/format.js';
test('classification date stays a calendar day under a foreign browser timezone',()=>{
 process.env.TZ='Pacific/Honolulu';assert.equal(formatDate('2026-11-01'),'01/11/2026');
 process.env.TZ='America/Los_Angeles';assert.equal(formatDate('2026-09-15'),'15/09/2026');
});
test('timestamps and default business day use Vietnam time',()=>{
 assert.equal(formatDate('2026-10-31T20:00:00Z'),'01/11/2026');
 assert.equal(todayVN(new Date('2026-10-31T20:00:00Z')),'2026-11-01');
 assert.match(formatTime('2026-10-31T20:00:00Z'),/03:00/);
 assert.equal(formatDate(null),'—');
});
