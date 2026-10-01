// Shared real authentication for the existing browser regression workflows.
module.exports=async function authenticate(page,url){
 const result=await page.request.post(url+'/api/auth/login',{data:{username:process.env.CCA_LAB_TEST_USERNAME||'admin',password:process.env.CCA_LAB_TEST_PASSWORD||'browser-password-1234'}});
 if(!result.ok())throw Error('Test login failed: '+await result.text());
 const session=await result.json();
 const projects=await page.request.get(url+'/api/projects').then(r=>r.json());
 const headers={'X-CSRF-Token':session.csrf,'X-Project-ID':projects[0].id};
 // Browser and APIRequestContext share cookies, but not per-request headers.
 for(const method of ['get','post','put','patch','delete']){
  const original=page.request[method].bind(page.request);
  page.request[method]=(target,options={})=>original(target,{...options,headers:{...headers,...options.headers}});
 }
};
