import { apply, availableActions, initialState } from './model.js';

let state = initialState();
const $ = (id) => document.getElementById(id);
const fmt = (x) => String(x).padStart(2, '0');

function render() {
  const actions = availableActions(state);
  $('copy-status').textContent = state.copy;
  $('copy-status').dataset.status = state.copy;
  $('location').textContent = state.location;
  $('loan-status').textContent = state.loan?.status || 'Sin préstamo';
  $('borrower').textContent = state.loan?.borrower || '—';
  $('transfer').textContent = state.transfer ? `${state.transfer.direction} · ${state.transfer.status}` : '—';
  for (const [key, flag] of [['race',actions.race],['advance',actions.advance],['activate',actions.activate],['return-good',actions.returnBook],['return-damaged',actions.returnBook],['retry',actions.retry]]) $(key).disabled = !flag;
  const phaseOrder = ['REQUESTED','ACTIVE','RETURNING','CLOSED'];
  const activeIndex = phaseOrder.indexOf(state.loan?.status);
  for (let i = 0; i < phaseOrder.length; i++) {
    const node = document.querySelector(`[data-phase="${phaseOrder[i]}"]`);
    node.classList.toggle('complete', activeIndex >= i);
    node.classList.toggle('current', activeIndex === i);
  }
  const list = $('event-list');
  list.replaceChildren(...state.log.map((item) => {
    const li = document.createElement('li');
    li.className = `event is-${item.tone}`;
    const head = document.createElement('div');
    const code = document.createElement('span');code.textContent = item.code;
    const title = document.createElement('strong');title.textContent = item.label;
    head.append(code,title);
    const detail = document.createElement('p');detail.textContent = item.detail;
    li.append(head,detail);
    return li;
  }));
  $('event-count').textContent = fmt(state.log.filter(x=>x.code==='202'||x.code==='200').length);
  $('conflict-count').textContent = fmt(state.log.filter(x=>x.code==='409').length);
}

document.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-action]');
  if (!button || button.disabled) return;
  const code = button.dataset.action;
  const action = code === 'RETURN_GOOD' ? {type:'RETURN',condition:'GOOD'} : code === 'RETURN_DAMAGED' ? {type:'RETURN',condition:'DAMAGED'} : {type:code};
  state = apply(state,action);
  render();
});

render();
