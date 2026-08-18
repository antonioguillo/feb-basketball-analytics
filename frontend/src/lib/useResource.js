import { useState, useEffect, useCallback } from 'react';

/**
 * Carga un recurso asíncrono y expone su estado.
 * `loader` debe devolver `{ data, source }` (ver `api/client.js`).
 * Las respuestas de una petición ya obsoleta se descartan.
 */
export function useResource(loader, deps = []) {
  const [state, setState] = useState({ status: 'loading', data: null, source: null, error: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setState((prev) => ({ ...prev, status: 'loading', error: null }));

    loader()
      .then(({ data, source }) => {
        if (active) setState({ status: 'ready', data, source, error: null });
      })
      .catch((error) => {
        if (active) setState({ status: 'error', data: null, source: null, error });
      });

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, retry };
}
