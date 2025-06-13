export const devtoolsOptions = (name) => ({
  name,
  trace: process.env.NODE_ENV === 'development',
  anonymousActionType: 'action',
  serialize: {
    options: {
      map: true,
      set: true,
      error: true,
      symbol: true,
      function: (fn) => fn.toString()
    }
  }
});