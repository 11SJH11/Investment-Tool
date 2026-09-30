// Isolated production verification: no dotenv reads or live dist replacement.
import path from 'node:path';
import {build} from 'vite';
const outDir = process.argv[2];
if (!outDir || !path.isAbsolute(outDir)) throw new Error('Provide an absolute verification output directory.');
await build({configLoader:'runner', envDir:false, build:{outDir, emptyOutDir:false}});
