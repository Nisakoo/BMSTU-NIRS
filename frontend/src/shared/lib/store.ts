import { writable } from 'svelte/store';

export function createStore<State, Action>(initial: State, reduce: (state: State, action: Action) => State) {
  let state = initial;
  const { subscribe, set } = writable(initial);
  return {
    subscribe,
    getState: () => state,
    dispatch(action: Action) {
      state = reduce(state, action);
      set(state);
    },
  };
}
