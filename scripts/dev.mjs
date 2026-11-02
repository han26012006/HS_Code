import {spawn} from 'node:child_process';
const args=process.argv.slice(2).filter(a=>a!=='--strictPort');
const child=spawn(process.env.CODEX_PRIMARY_RUNTIME_PYTHON||(process.platform==='win32'?'python':'python3'),['serve.py',...args],{stdio:'inherit',env:process.env});
for(const s of ['SIGINT','SIGTERM'])process.on(s,()=>child.kill(s));
child.on('exit',code=>process.exit(code??0));
