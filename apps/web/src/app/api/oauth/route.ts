import {NextRequest,NextResponse} from "next/server";
import {authReturnPath,authFailurePath} from "@/lib/auth-destination";
import {authConfig,authFetch,canonicalOrigin,createChallenge,noStore,sameSiteLogin,setFlowCookie} from "@/lib/auth";

export const dynamic="force-dynamic";
export const runtime="nodejs";

async function googleStatus(config:NonNullable<ReturnType<typeof authConfig>>):Promise<"enabled"|"disabled"|"unknown">{
  try {
    const reply=await authFetch(config,"settings");
    if(reply.status!==200 || !reply.data || typeof reply.data!=="object")return "unknown";
    const external=(reply.data as {external?:{google?:unknown}}).external;
    return external?.google===true?"enabled":external?.google===false?"disabled":"unknown";
  }catch{return "unknown";}
}
export async function GET(request:NextRequest){
  const action=request.nextUrl.searchParams.get("action")||"start";
  const config=authConfig();
  const origin=canonicalOrigin();
  if(action==="status"){
    if(!config)return noStore(NextResponse.json({provider:"google",state:"unknown",mode:"pkce",passwordRequired:false},{status:503}));
    const state=await googleStatus(config);
    return noStore(NextResponse.json({provider:"google",state,mode:"pkce",passwordRequired:false}));
  }
  if(action!=="start")return noStore(NextResponse.json({error:"INVALID_ACTION"},{status:400}));
  const returnTo=authReturnPath(request.nextUrl.searchParams.get("next"));
  const fail=(reason:string)=>noStore(NextResponse.redirect(new URL(authFailurePath(returnTo,reason),origin||request.url),303));
  if(!config||!origin)return fail("not_configured");
  if(!sameSiteLogin(request))return noStore(NextResponse.json({error:"CROSS_SITE_LOGIN_BLOCKED"},{status:403}));
  if(request.nextUrl.host!==new URL(origin).host)return noStore(NextResponse.redirect(origin+"/",303));
  const state=await googleStatus(config);
  if(state!=="enabled")return fail(state==="disabled"?"google_disabled":"provider_unavailable");
  const {verifier,challenge}=createChallenge();
  const target=new URL(config.url+"/auth/v1/authorize");
  target.searchParams.set("provider","google");
  target.searchParams.set("redirect_to",origin+"/api/oauth-callback");
  target.searchParams.set("code_challenge",challenge);
  target.searchParams.set("code_challenge_method","s256");
  const response=NextResponse.redirect(target,302);
  setFlowCookie(response,verifier);
  response.cookies.set("__Host-capstone_return",returnTo,{httpOnly:true,secure:true,sameSite:"lax",path:"/",maxAge:300});
  return noStore(response);
}
