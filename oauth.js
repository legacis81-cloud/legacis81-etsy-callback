/* No token exchange or external requests. Tokens exist only in the private runner. */
(function () {
  'use strict';
  const redirectUri = 'https://legacis81-cloud.github.io/legacis81-etsy-callback/';
  const storageKey = 'etsy_oauth_session_v2';
  const ttl = 15 * 60 * 1000;
  function validateCallback(params, session, now) {
    if (!session || !Number.isFinite(session.created_at) || now < session.created_at || now - session.created_at > ttl ||
        params.getAll('code').length !== 1 || params.getAll('state').length !== 1 || params.has('error') ||
        !params.get('code') || params.get('state') !== session.state ||
        !/^[A-Za-z0-9._~-]{43,128}$/.test(session.code_verifier) ||
        typeof session.state !== 'string' || session.state.length < 32 ||
        typeof session.client_id !== 'string' || !session.client_id) {
      throw new Error('Invalid or expired callback');
    }
    return { ...session, code: params.get('code'), returned_state: params.get('state'), redirect_uri: redirectUri };
  }
  function base64url(buffer) {
    return btoa(String.fromCharCode(...new Uint8Array(buffer))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  function randomString() { return base64url(crypto.getRandomValues(new Uint8Array(48))); }
  async function challenge(verifier) {
    return base64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)));
  }
  if (typeof module !== 'undefined') module.exports = { validateCallback, challenge, redirectUri };
  if (typeof document === 'undefined') return;
  const el = id => document.getElementById(id);
  const status = message => { el('status').textContent = message; };
  const reset = () => {
    sessionStorage.removeItem(storageKey);
    ['etsy_verifier', 'etsy_state', 'etsy_client_id'].forEach(k => sessionStorage.removeItem(k));
  };
  let expiryTimer;
  function clearPackage() {
    clearTimeout(expiryTimer);
    el('package').value = '';
    el('handoff').hidden = true;
    el('restart').hidden = false;
  }
  el('restart').onclick = () => window.location.assign(redirectUri);
  el('clear').onclick = () => { clearPackage(); status('Package cleared. Complete the private workflow, or start again if needed.'); };
  el('copy').onclick = async () => {
    try { await navigator.clipboard.writeText(el('package').value); status('Copied. Paste only into the private GitHub Actions secret.'); }
    catch (_) { el('package').select(); status('Select and copy the package manually into the private secret.'); }
  };
  el('connect').onclick = async () => {
    const client_id = el('clientId').value.trim();
    if (!el('ready').checked || !/^[A-Za-z0-9_-]+$/.test(client_id)) {
      status('Complete storage preflight and enter only your API Keystring.'); return;
    }
    el('connect').disabled = true;
    try {
      reset();
      const session = { client_id, code_verifier: randomString(), state: randomString(), created_at: Date.now() };
      const code_challenge = await challenge(session.code_verifier);
      sessionStorage.setItem(storageKey, JSON.stringify(session));
      const params = new URLSearchParams({response_type: 'code', client_id, redirect_uri: redirectUri,
        scope: 'shops_r listings_r', state: session.state, code_challenge, code_challenge_method: 'S256'});
      window.location.assign('https://www.etsy.com/oauth/connect?' + params);
    } catch (_) { reset(); el('connect').disabled = false; status('Unable to prepare authorization. Allow session storage and try again.'); }
  };
  const params = new URLSearchParams(window.location.search);
  if (['code', 'state', 'error'].some(k => params.has(k))) {
    history.replaceState({}, document.title, window.location.pathname);
    el('start').hidden = true;
    el('restart').hidden = false;
    try {
      const session = JSON.parse(sessionStorage.getItem(storageKey));
      reset(); // Consume local state once, including failed callbacks.
      const handoff = validateCallback(params, session, Date.now());
      el('package').value = JSON.stringify(handoff);
      el('handoff').hidden = false;
      status('Authorization verified locally. Tokens have not yet been requested or stored.');
      expiryTimer = setTimeout(() => { clearPackage(); status('Authorization package expired. Start again.'); }, session.created_at + ttl - Date.now());
    } catch (_) { reset(); status('Authorization denied, invalid or expired. Start again in this same browser tab.'); }
  }
})();
