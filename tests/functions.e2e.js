// Teste manual de ponta a ponta das funções no emulador (sem chamar o Gemini de verdade)
import { initializeApp } from 'firebase/app';
import { connectAuthEmulator, createUserWithEmailAndPassword, getAuth } from 'firebase/auth';
import { connectFirestoreEmulator, doc, getDoc, getFirestore, setDoc, updateDoc } from 'firebase/firestore';
import { connectFunctionsEmulator, getFunctions, httpsCallable } from 'firebase/functions';

const app = initializeApp({ apiKey: 'demo', projectId: 'demo-studytimeia' });
const auth = getAuth(app); connectAuthEmulator(auth, 'http://127.0.0.1:9099', { disableWarnings: true });
const db = getFirestore(app); connectFirestoreEmulator(db, '127.0.0.1', 8080);
const fns = getFunctions(app, 'southamerica-east1'); connectFunctionsEmulator(fns, '127.0.0.1', 5001);
const call = (name, data) => httpsCallable(fns, name)(data).then((r) => r.data, (e) => `ERRO ${e.code}: ${e.message}`);

console.log('sem login:', await call('trackStudyMinute'));
const { user } = await createUserWithEmailAndPassword(auth, 'teste@x.com', '123456');
const ref = doc(db, 'users', user.uid);
await setDoc(ref, { email: 'teste@x.com', plan: 'free', goal: null, studyDays: [], studyDate: '2000-01-01', minutesToday: 0 });
console.log('sem dias de estudo:', await call('trackStudyMinute'));
await updateDoc(ref, { goal: 'TRT', studyDays: ['dom', 'seg', 'ter', 'qua'] });
const today = ['dom','seg','ter','qua','qui','sex','sab'][new Date(Date.now() - 3*3600e3).getUTCDay()];
console.log('hoje é', today, '(o teste precisa de um dia escolhido)');
await updateDoc(ref, { goal: 'TRT', studyDays: [today] });
console.log('1º minuto:', await call('trackStudyMinute'));
console.log('2º minuto logo em seguida (deve ser ignorado):', await call('trackStudyMinute'));
console.log('histórico inválido:', await call('askTutor', { history: [{ role: 'model', text: 'oi' }] }));
console.log('pergunta (Gemini falso => indisponível):', await call('askTutor', { history: [{ role: 'user', text: 'oi' }] }));
const snap = await getDoc(ref);
console.log('perfil no banco:', JSON.stringify(snap.data()));
process.exit(0);
