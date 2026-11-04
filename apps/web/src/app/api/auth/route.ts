import {NextRequest,NextResponse} from "next/server";
import {ACCESS_COOKIE,REFRESH_COOKIE,authConfig,authFetch,clearSessionCookies,noStore,originAllowed,session,setSessionCookies} from "@/lib/auth";
export const dynamic="force-dynamic";
export const runtime="nodejs";

export async function GET(request:NextRequest){
  const user=await session(request.cookies.get(ACCESS_COOKIE)?.value,request.cookies.get(REFRESH_COOKIE)?.value);
  const response=user.status===200
    ? NextResponse.json({ok:true,user:{email:user.email,authenticated:true}})
    : NextResponse.json({error:user.reason},{status:user.status});
  if(user.status===200 && user.tokens)setSessionCookies(response,user.tokens);
  if(user.status!==200 && user.clear)clearSessionCookies(response);
  return noStore(response);
}
export async function POST(request:NextRequest){
  if(!originAllowed(request))return noStore(NextResponse.json({error:"ORIGIN_NOT_ALLOWED"},{status:403}));
  const declared=Number(request.headers.get("content-length")||0);
  if(declared>4600)return noStore(NextResponse.json({error:"REQUEST_TOO_LARGE"},{status:413}));
  if(!/^application\/json(?:;|$)/i.test(request.headers.get("content-type")||""))
    return noStore(NextResponse.json({error:"INVALID_CONTENT_TYPE"},{status:415}));
  let body:unknown;
  try {const raw=await request.text();if(raw.length>4600)throw Error("large");body=JSON.parse(raw)}catch{
    return noStore(NextResponse.json({error:"INVALID_REQUEST"},{status:400}));
  }
  if(!body || typeof body!=="object" || Array.isArray(body) || (body as {action?:string}).action!=="logout")
    return noStore(NextResponse.json({error:"INVALID_ACTION"},{status:400}));
  const config=authConfig();
  const token=request.cookies.get(ACCESS_COOKIE)?.value;
  const response=NextResponse.json({ok:true});
  clearSessionCookies(response);
  // Local deletion is not evidence that a still-live refresh session was revoked.
  if((!config || !token) && (token || request.cookies.get(REFRESH_COOKIE)?.value))
    return noStore(NextResponse.json({error:"LOGOUT_REVOCATION_UNCONFIRMED"},{status:503,headers:response.headers}));
  if(config && token){
    try{
      const revoke=await authFetch(config,"logout?scope=local",{method:"POST",accessToken:token,body:{}});
      if(revoke.status<200||revoke.status>=300)return noStore(NextResponse.json({error:"LOGOUT_REVOCATION_UNCONFIRMED"},{status:503,headers:response.headers}));
    }catch{return noStore(NextResponse.json({error:"LOGOUT_REVOCATION_UNCONFIRMED"},{status:503,headers:response.headers}))}
  }
  return noStore(response);
}
