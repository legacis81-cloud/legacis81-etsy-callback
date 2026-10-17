const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { webcrypto } = require('node:crypto');
global.crypto = webcrypto;
const { validateCallback, challenge } = require('../oauth.js');
const session = {client_id:'client', state:'s'.repeat(64), code_verifier:'v'.repeat(64), created_at:1000000};
const params = () => new URLSearchParams({code:'code', state:session.state});
test('valid callback creates handoff without requesting tokens', () => {
  const result = validateCallback(params(), session, 1000001);
  assert.equal(result.code_verifier, session.code_verifier);
  assert.equal(result.returned_state, session.state);
});
test('reject state mismatch, expiry, future session, duplicates, denial, missing session', () => {
  assert.throws(()=>validateCallback(new URLSearchParams({code:'c',state:'wrong'}),session,1000001));
  assert.throws(()=>validateCallback(params(),session,1900001));
  assert.throws(()=>validateCallback(params(),session,999999));
  const duplicate=params(); duplicate.append('code','other');
  assert.throws(()=>validateCallback(duplicate,session,1000001));
  const denied=params(); denied.set('error','access_denied');
  assert.throws(()=>validateCallback(denied,session,1000001));
  assert.throws(()=>validateCallback(params(),null,1000001));
});
test('PKCE RFC 7636 known vector', async () => {
  assert.equal(await challenge('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'), 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM');
});
test('no browser token endpoint or fetch, restrictive network CSP', () => {
  assert(!fs.readFileSync('oauth.js','utf8').includes('fetch('));
  assert(fs.readFileSync('index.html','utf8').includes("connect-src 'none'"));
});
