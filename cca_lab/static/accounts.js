'use strict';
window.accountState={user:null,csrf:null,projects:[],project:null,ready:false};
const originalFetch=window.fetch.bind(window);
window.fetch=(input,options={})=>{
 const url=new URL(typeof input==='string'?input:input.url,location.href);
 if(url.origin===location.origin&&url.pathname.startsWith('/api/')){
  const headers=new Headers(options.headers||(input instanceof Request?input.headers:undefined));
  if(accountState.csrf)headers.set('X-CSRF-Token',accountState.csrf);
  if(accountState.project)headers.set('X-Project-ID',accountState.project.id);
  options={...options,headers};
 }
 return originalFetch(input,options).then(response=>{
  if(response.status===401&&accountState.ready){accountState.ready=false;location.reload();}
  return response;
 });
};
function projectURL(value){
 const url=new URL(value,location.href);
 if(url.origin===location.origin&&url.pathname.startsWith('/api/')&&accountState.project)url.searchParams.set('project_id',accountState.project.id);
 return url.pathname+url.search+url.hash;
}
async function accountAPI(path,method='GET',body){
 const response=await fetch('/api'+path,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
 const value=await response.json();if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));return value;
}
function accountError(error){document.querySelector('#account-error').textContent=error.message;}
function accountPanel(title,html){
 document.querySelector('#account-title').textContent=title;document.querySelector('#account-content').innerHTML=html;document.querySelector('#account-error').textContent='';
 const dialog=document.querySelector('#account-dialog');if(!dialog.open)dialog.showModal();
}
function renderAccountBar(){
 const s=accountState;
 document.querySelector('#project-selector').innerHTML=s.projects.map(p=>`<option value="${esc(p.id)}" ${p.id===s.project?.id?'selected':''}>${esc(p.name)}</option>`).join('');
 document.querySelector('#project-role').textContent=s.project?({admin:'Project administrator',regular:'Regular user',view:'View-only'})[s.project.role]:'No projects yet';
 document.querySelector('#account-name').textContent=s.user.username;
 document.querySelector('#manage-members').hidden=s.project?.role!=='admin';
 document.querySelector('#manage-users').hidden=!s.user.is_admin;
 document.body.dataset.projectRole=s.project?.role||'none';
}
async function loadProjects(preferred){
 accountState.projects=await accountAPI('/projects');
 accountState.project=accountState.projects.find(p=>p.id===(preferred||sessionStorage.getItem('cca-project')))||accountState.projects[0]||null;
 if(accountState.project)sessionStorage.setItem('cca-project',accountState.project.id);
 renderAccountBar();
}
async function openMembers(){
 const pid=accountState.project.id,members=await accountAPI('/projects/'+pid+'/members');
 accountPanel('Project members',`<p>Manage access to <strong>${esc(accountState.project.name)}</strong>.</p><form id="rename-project"><label>Project name<input name="name" required maxlength="120" value="${esc(accountState.project.name)}"></label><button>Rename</button></form><div class="table-wrap"><table><thead><tr><th>User</th><th>Role</th><th>Actions</th></tr></thead><tbody>${members.map(m=>`<tr><td>${esc(m.username)}${m.active?'':' (disabled)'}</td><td><select data-member-role="${m.id}">${['admin','regular','view'].map(r=>`<option ${r===m.role?'selected':''} value="${r}">${{admin:'Admin',regular:'Regular user',view:'View-only'}[r]}</option>`).join('')}</select></td><td><button data-save-member="${esc(m.username)}" data-user-id="${m.id}">Save</button> <button data-remove-member="${m.id}">Remove</button></td></tr>`).join('')}</tbody></table></div><form id="add-member"><h3>Add a registered user</h3><label>Username<input name="username" required autocomplete="off"></label><label>Role<select name="role"><option value="regular">Regular user</option><option value="view">View-only</option><option value="admin">Admin</option></select></label><button class="primary">Add member</button></form>`);
 document.querySelector('#add-member').onsubmit=async e=>{e.preventDefault();try{await accountAPI('/projects/'+pid+'/members','PUT',Object.fromEntries(new FormData(e.target)));await openMembers();}catch(error){accountError(error)}};
 document.querySelector('#rename-project').onsubmit=async e=>{e.preventDefault();try{await accountAPI('/projects/'+pid,'PATCH',Object.fromEntries(new FormData(e.target)));await loadProjects(pid);await openMembers();}catch(error){accountError(error)}};
}
async function openUsers(){
 const users=await accountAPI('/admin/users');
 accountPanel('User administration',`<p>Site administrators manage accounts. Project membership controls access to project content.</p><div class="table-wrap"><table><thead><tr><th>Username</th><th>Active</th><th>Site admin</th><th>New password (optional)</th><th></th></tr></thead><tbody>${users.map(u=>`<tr data-account-user="${u.id}"><td>${esc(u.username)}</td><td><input type="checkbox" name="active" ${u.active?'checked':''}></td><td><input type="checkbox" name="is_admin" ${u.is_admin?'checked':''}></td><td><input type="password" name="password" minlength="12" autocomplete="new-password" aria-label="New password for ${esc(u.username)}"></td><td><button data-save-user="${u.id}">Save</button></td></tr>`).join('')}</tbody></table></div><p class="small">Disabling an account or saving changes revokes its sessions. A last active administrator cannot be removed.</p><form id="admin-create-user"><h3>Create account</h3><label>Username<input name="username" required minlength="3" maxlength="64" autocomplete="off"></label><label>Initial password<input type="password" name="password" required minlength="12" maxlength="256" autocomplete="new-password"></label><button class="primary">Create user</button></form>`);
 document.querySelector('#admin-create-user').onsubmit=async e=>{e.preventDefault();try{await accountAPI('/admin/users','POST',Object.fromEntries(new FormData(e.target)));await openUsers();}catch(error){accountError(error)}};
}
function enforceProjectUI(){
 if(!accountState.ready)return;
 const readOnly=accountState.project?.role==='view';
 document.querySelector('#primary').hidden=readOnly||!accountState.project;
 if(readOnly){
  const allowed=/^(job-detail|evaluation-detail|prediction-detail|download-task|cca-export|dataset-preview|gold-preview|errors-|request-|evaluation-predictions-|results-|agreement-load$|workflow-filter$|snapshot$|close-detail$)/;
  document.querySelectorAll('[data-action]').forEach(el=>{if(!allowed.test(el.dataset.action)&&!el.closest('#account-dialog'))el.hidden=true;});
  document.querySelectorAll('.task-import-panel').forEach(el=>el.hidden=true);
 }
 document.querySelectorAll('a[href^="/api/"],img[src^="/api/"]').forEach(el=>{const key=el.tagName==='IMG'?'src':'href',old=el.getAttribute(key),next=projectURL(old);if(old!==next)el.setAttribute(key,next);});
}
document.addEventListener('DOMContentLoaded',async()=>{
 document.querySelector('#sign-in-form').onsubmit=async e=>{
  e.preventDefault();const mode=e.submitter.value,data=Object.fromEntries(new FormData(e.target));
  try{if(mode==='register'){await accountAPI('/auth/register','POST',data);document.querySelector('#login-error').textContent='Account registered. Sign in to create a project or receive an invitation.';return;}
   await accountAPI('/auth/login','POST',data);location.reload();
  }catch(error){document.querySelector('#login-error').textContent=error.message;}
 };
 document.querySelector('#project-selector').onchange=e=>{sessionStorage.setItem('cca-project',e.target.value);location.reload();};
 document.querySelector('#new-project').onclick=()=>{accountPanel('Create project','<form id="create-project"><label>Project name<input name="name" required maxlength="120"></label><button class="primary">Create project</button></form>');document.querySelector('#create-project').onsubmit=async e=>{e.preventDefault();try{const p=await accountAPI('/projects','POST',Object.fromEntries(new FormData(e.target)));sessionStorage.setItem('cca-project',p.id);location.reload();}catch(error){accountError(error)}};};
 document.querySelector('#manage-members').onclick=()=>openMembers().catch(accountError);
 document.querySelector('#manage-users').onclick=()=>openUsers().catch(accountError);
 document.querySelector('#logout').onclick=async()=>{try{await accountAPI('/auth/logout','POST');location.reload();}catch(e){toast(e.message)}};
 document.querySelector('#change-password').onclick=()=>{accountPanel('Change password','<form id="password-change"><label>Current password<input type="password" name="current_password" required autocomplete="current-password"></label><label>New password<input type="password" name="password" required minlength="12" maxlength="256" autocomplete="new-password"></label><button class="primary">Change and sign out</button></form>');document.querySelector('#password-change').onsubmit=async e=>{e.preventDefault();try{await accountAPI('/auth/password','POST',Object.fromEntries(new FormData(e.target)));location.reload();}catch(error){accountError(error)}};};
 document.querySelector('#account-close').onclick=()=>document.querySelector('#account-dialog').close();
 try{
  const session=await accountAPI('/auth/me');Object.assign(accountState,session);await loadProjects();accountState.ready=true;
  document.body.classList.add('signed-in');
  if(accountState.project)await refresh();else{document.querySelector('#title').textContent='Welcome to CCA-Lab';document.querySelector('#view').innerHTML='<div class="panel empty"><h2>Create your first project</h2><p>Use New project in the sidebar, or ask a project administrator to add your username.</p></div>';}
 }catch(error){if(accountState.user)document.querySelector('#login-error').textContent=error.message;}
 new MutationObserver(enforceProjectUI).observe(document.body,{childList:true,subtree:true});enforceProjectUI();
});
document.addEventListener('click',async e=>{
 const el=e.target.closest('[data-save-member],[data-remove-member],[data-save-user]');if(!el)return;
 try{
  if(el.dataset.saveMember){await accountAPI('/projects/'+accountState.project.id+'/members','PUT',{username:el.dataset.saveMember,role:document.querySelector(`[data-member-role="${el.dataset.userId}"]`).value});if((el.dataset.userId||el.dataset.removeMember)===accountState.user.id)location.reload();else await openMembers();}
  if(el.dataset.removeMember){if(!confirm('Remove this project membership?'))return;await accountAPI('/projects/'+accountState.project.id+'/members/'+el.dataset.removeMember,'DELETE');if((el.dataset.userId||el.dataset.removeMember)===accountState.user.id)location.reload();else await openMembers();}
  if(el.dataset.saveUser){const row=el.closest('tr'),body={active:row.querySelector('[name=active]').checked,is_admin:row.querySelector('[name=is_admin]').checked};const password=row.querySelector('[name=password]').value;if(password)body.password=password;await accountAPI('/admin/users/'+el.dataset.saveUser,'PATCH',body);await openUsers();}
 }catch(error){accountError(error);}
});
