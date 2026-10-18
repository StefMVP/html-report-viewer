import { b } from './cycle-b.mjs';
export const a = 'A';
export function cycle() { return a + b; }
