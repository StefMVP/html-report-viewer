import { label } from './parts/label.mjs';
import { cycle } from './cycle-a.mjs';
import data from './data.json' with { type: 'json' };
const late = await import('./parts/late.mjs');
// import './not-a-dependency.mjs';
const example = "import './also-not-a-dependency.mjs'";
document.querySelector('#module-result').textContent = [label, cycle(), data.value, late.value].join(' ');
