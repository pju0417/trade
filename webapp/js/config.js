// Servers = Firebase projects (free plan: up to 100 devices connected at once per project).
// Empty list = local test mode (teacher and students in tabs of ONE browser).
// The order is the server number in room codes ("1-K7QPM-2" = SERVERS[0]): never reorder or
// delete a server that has been used; add new servers at the end. See webapp/FIREBASE_SETUP.md.
// Web config values are public identifiers, not secrets; access is governed by the database rules.
export const SERVERS = [
  {
    name: '1서버',
    capacity: 90,
    firebase: {
      apiKey: 'AIzaSyC3fuET5qqla_sxlX-Tv18z7UkTaAZNbjE',
      authDomain: 'trade-a55c6.firebaseapp.com',
      databaseURL: 'https://trade-a55c6-default-rtdb.asia-southeast1.firebasedatabase.app',
      projectId: 'trade-a55c6',
      storageBucket: 'trade-a55c6.firebasestorage.app',
      messagingSenderId: '1016867007785',
      appId: '1:1016867007785:web:f08facba4ee0088f3edb38',
    },
  },
];
