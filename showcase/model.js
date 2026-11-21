/**
 * Browser-only domain illustration of Library Network API.
 * It is deliberately NOT the FastAPI application or a PostgreSQL emulator.
 * Real concurrency guarantees are tested by the backend repository.
 */
export const COPY_ID = 'CP-0001';

export function initialState() {
  return {
    copy: 'AVAILABLE', loan: null, transfer: null, condition: 'GOOD',
    location: 'Central', requestKeys: {}, latestKey: null, raceSequence: 0, step: 0,
    log: [{ id: 0, code: 'READY', label: 'Ejemplo listo', detail: 'Ejemplar CP-0001 en Biblioteca Central; sin préstamo abierto.', tone: 'info' }],
  };
}

function record(state, code, label, detail, tone = 'info') {
  const step = state.step + 1;
  return { ...state, step, log: [{ id: step, code, label, detail, tone }, ...state.log].slice(0, 24) };
}

export function apply(state, action) {
  if (action.type === 'RESET') return initialState();
  if (action.type === 'RACE') {
    const sequence = state.raceSequence + 1;
    const first = apply({ ...state, raceSequence: sequence }, { type: 'REQUEST', member: 'Norte', key: `race-${sequence}-norte` });
    return apply(first, { type: 'REQUEST', member: 'Sur', key: `race-${sequence}-sur` });
  }
  if (action.type === 'REQUEST') {
    const member = action.member;
    const key = action.key;
    if (!['Norte', 'Sur'].includes(member) || !key) return record(state, '400', 'Solicitud inválida', 'Sucursal o clave de idempotencia incorrecta.', 'error');
    if (state.requestKeys[key]) {
      if (state.requestKeys[key] === member) return record(state, '200', 'Reintento idempotente', `La clave ${key} recupera la respuesta; no crea un segundo préstamo.`, 'success');
      return record(state, '409', 'Clave reutilizada con otro cuerpo', 'Misma clave de idempotencia, contenido distinto: operación rechazada.', 'error');
    }
    if (state.copy !== 'AVAILABLE' || state.loan && state.loan.status !== 'CLOSED') return record(state, '409', 'Ejemplar ya comprometido', `Solicitud de ${member} rechazada: el ejemplar no se puede prometer dos veces.`, 'error');
    return record({ ...state, copy: 'RESERVED', loan: { borrower: member, status: 'REQUESTED' },
      transfer: { direction: 'OUTBOUND', status: 'PREPARED' },
      requestKeys: { ...state.requestKeys, [key]: member }, latestKey: key }, '202', 'Préstamo solicitado', `${member} reserva CP-0001. Préstamo + traslado + clave se confirman juntos.`, 'success');
  }
  if (action.type === 'ADVANCE') {
    const transfer = state.transfer;
    if (!transfer || transfer.status === 'RECEIVED') return record(state, '409', 'Transición ilegal', 'No hay un traslado pendiente que pueda avanzar.', 'error');
    const steps = { PREPARED: 'DISPATCHED', DISPATCHED: 'IN_TRANSIT', IN_TRANSIT: 'RECEIVED' };
    const nextStatus = steps[transfer.status];
    if (!nextStatus) return record(state, '409', 'Transición ilegal', 'La máquina de estados rechaza saltos y retrocesos.', 'error');
    const patch = { ...state, transfer: { ...transfer, status: nextStatus } };
    if (nextStatus !== 'RECEIVED') {
      if (nextStatus === 'DISPATCHED') patch.copy = 'IN_TRANSIT';
      return record(patch, '200', `Traslado ${nextStatus}`, 'Cada avance respeta el estado inmediatamente anterior. La ubicación física no cambia todavía.', 'success');
    }
    if (transfer.direction === 'OUTBOUND') {
      patch.location = state.loan.borrower;
      patch.copy = 'RESERVED';
      return record(patch, '200', 'Traslado recibido', `El ejemplar llegó a ${patch.location}; todavía falta activar el préstamo.`, 'success');
    }
    patch.location = 'Central';
    patch.copy = state.condition === 'DAMAGED' ? 'RETIRED' : 'AVAILABLE';
    patch.loan = { ...state.loan, status: 'CLOSED' };
    return record(patch, '200', 'Devolución recibida en origen', `Préstamo cerrado. El ejemplar queda ${patch.copy}; recién ahora puede liberarse si está sano.`, 'success');
  }
  if (action.type === 'ACTIVATE') {
    if (state.loan?.status !== 'REQUESTED' || state.transfer?.direction !== 'OUTBOUND' || state.transfer?.status !== 'RECEIVED') {
      return record(state, '409', 'Activación bloqueada', 'La sucursal debe confirmar recepción antes de prestar el ejemplar.', 'error');
    }
    return record({ ...state, loan: { ...state.loan, status: 'ACTIVE' }, copy: 'ON_LOAN' }, '200', 'Préstamo activo', `El socio de ${state.loan.borrower} retiró el libro.`, 'success');
  }
  if (action.type === 'RETURN') {
    if (state.loan?.status !== 'ACTIVE') return record(state, '409', 'Devolución bloqueada', 'Solo se puede devolver un préstamo activo.', 'error');
    const condition = action.condition === 'DAMAGED' ? 'DAMAGED' : 'GOOD';
    return record({ ...state, loan: { ...state.loan, status: 'RETURNING' }, copy: 'PENDING_RETURN', condition,
      transfer: { direction: 'RETURN', status: 'PREPARED' } }, '200', 'Devolución iniciada', `Estado físico: ${condition}. La copia sigue bloqueada hasta llegar a Central.`, 'success');
  }
  if (action.type === 'RETRY') {
    if (!state.latestKey) return record(state, '409', 'Sin solicitud que reintentar', 'Primero simulá las dos solicitudes.', 'error');
    return apply(state, { type: 'REQUEST', member: state.requestKeys[state.latestKey], key: state.latestKey });
  }
  if (action.type === 'ALTER') return apply(state, { type: 'REQUEST', member: 'Sur', key: state.latestKey || '' });
  if (action.type === 'INVALID') return record(state, '409', 'Salto de estado rechazado', 'No se puede marcar RECEIVED sin pasar por DISPATCHED e IN_TRANSIT.', 'error');
  return state;
}

export function availableActions(state) {
  const transferPending = state.transfer && state.transfer.status !== 'RECEIVED';
  return {
    race: !state.loan || state.loan.status === 'CLOSED' && state.copy === 'AVAILABLE',
    advance: Boolean(transferPending),
    activate: state.loan?.status === 'REQUESTED' && state.transfer?.status === 'RECEIVED',
    returnBook: state.loan?.status === 'ACTIVE',
    retry: Boolean(state.latestKey),
  };
}
