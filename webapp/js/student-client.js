// Student-side API. A UI (any framework) only needs this object:
//
//   const me = new StudentClient({ transport, country: 'Tropia', token: '4821' })
//   me.onState((state) => render(state))     // full state of my country, see webapp/API.md
//   await me.connect()                       // -> {ok, msg}
//   await me.list('banana', 3, 12)           // every action resolves to {ok, msg, ...}
//
// Actions are checked by the teacher's engine; a refused action returns ok:false and a
// Korean message that can be shown to the student as is.

export class StudentClient {
  constructor({ transport, country, token }) {
    this.transport = transport;
    this.country = country;
    this.token = String(token);
    this.state = null;
    this.listeners = new Set();
  }

  onState(fn) {
    this.listeners.add(fn);
    if (this.state) fn(this.state);
    return () => this.listeners.delete(fn);
  }

  async connect() {
    await this.transport.studentStart(this.country, (json) => {
      this.state = JSON.parse(json);
      for (const fn of this.listeners) fn(this.state);
    });
    return this.send({ type: 'hello' });
  }

  async send(action) {
    try {
      return await this.transport.send(this.country, this.token, action);
    } catch (e) {
      return { ok: false, msg: String(e.message || e) };
    }
  }

  // market (phases: listing, trading; buying only in trading)
  list(good, qty, price, gen = 1) { return this.send({ type: 'list', good, gen, qty, price }); }
  cancel(oid) { return this.send({ type: 'cancel', oid }); }
  reprice(oid, price) { return this.send({ type: 'reprice', oid, price }); }
  buy(oid, qty) { return this.send({ type: 'buy', oid, qty }); }

  // direct offers (trading). give/get: {good, qty, gen?}; cash: whole G
  offerSell(to, give, cash) { return this.send({ type: 'offer', kind: 'sell', to, give, cash }); }
  offerBuy(to, get, cash) { return this.send({ type: 'offer', kind: 'buy', to, get, cash }); }
  offerBarter(to, give, get) { return this.send({ type: 'offer', kind: 'barter', to, give, get }); }
  respond(offerId, accept) { return this.send({ type: 'respond', offer: offerId, accept: !!accept }); }
  withdraw(offerId) { return this.send({ type: 'withdraw', offer: offerId }); }

  // investment phase
  invest(good) { return this.send({ type: 'invest', good }); }
  focus(good) { return this.send({ type: 'focus', good }); }
}
