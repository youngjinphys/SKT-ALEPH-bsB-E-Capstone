import {createHash,randomBytes} from "node:crypto";
import type {NextRequest} from "next/server";
import type {NextResponse} from "next/server";

export const ACCESS_COOKIE = "__Host-capstone_at";
export const REFRESH_COOKIE = "__Host-capstone_rt";
export const FLOW_COOKIE = "__Host-capstone_pkce";
type AuthConfig = {url:string;key:string};
type AuthUser = {id:string;email:string;email_confirmed_at?:string|null;confirmed_at?:string|null};
type TokenResponse = {access_token:string;refresh_token:string;expires_in?:number};
export type Session = {status:200;email:string;tokens?:TokenResponse} | {status:401|403|503;reason:string;clear?:boolean};

export function authConfig(env:Record<string,string|undefined>=process.env):AuthConfig|null {
  const url=(env.SUPABASE_URL||"").trim(),key=(env.SUPABASE_PUBLISHABLE_KEY||"").trim();
  if(!/^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(url))return null;
  if(!/^(sb_publishable_[a-zA-Z0-9_-]+|eyJ[a-zA-Z0-9_.-]+)$/.test(key))return null;
  return {url,key};
}
export function canonicalOrigin(env:Record<string,string|undefined>=process.env):string|null {
  try {
    const value=env.CAPSTONE_SITE_ORIGIN||"";
    const url=new URL(value);
    if(url.protocol!=="https:" || url.username || url.password || url.pathname!=="/" || url.search || url.hash || value!==url.origin)return null;
    return url.origin;
  } catch{return null;}
}
export function originAllowed(request:NextRequest):boolean {
  const origin=request.headers.get("origin");
  if(!origin)return false;
  const hosts=[canonicalOrigin(),process.env.VERCEL_URL && /^[-a-z0-9]+\.vercel\.app$/i.test(process.env.VERCEL_URL) ? "https://"+process.env.VERCEL_URL : null].filter(Boolean);
  const site=request.headers.get("sec-fetch-site");
  return hosts.includes(origin)&&(site===null || site==="same-origin" || site==="none");
}
export function validToken(value:unknown):value is string {
  return typeof value==="string" && value.length>12 && value.length<=8192 && /^[a-zA-Z0-9._~-]+$/.test(value);
}
function isUser(value:unknown):value is AuthUser {
  if(!value || typeof value!=="object")return false;
  const user=value as AuthUser;
  return typeof user.id==="string" && Boolean(user.id) && typeof user.email==="string" && Boolean(user.email);
}
function allowedUser(value:unknown):value is AuthUser {
  if(!value || typeof value!=="object")return false;
  const user=value as AuthUser;
  if(typeof user.id!=="string" || typeof user.email!=="string" || !(user.email_confirmed_at||user.confirmed_at))return false;
  const allow=(process.env.CAPSTONE_ALLOWED_EMAILS||"").split(",").map(s=>s.trim().toLowerCase()).filter(Boolean);
  return !allow.length || allow.includes(user.email.toLowerCase());
}
export async function authFetch(config:AuthConfig,path:string,options:{method?:"GET"|"POST";body?:Record<string,string>;accessToken?:string}={}) {
  const headers:Record<string,string>={apikey:config.key,Accept:"application/json"};
  if(options.body)headers["Content-Type"]="application/json";
  if(options.accessToken)headers.Authorization="Bearer "+options.accessToken;
  const response=await fetch(config.url+"/auth/v1/"+path,{method:options.method||"GET",headers,
    ...(options.body?{body:JSON.stringify(options.body)}:{}),
    cache:"no-store",redirect:"error",signal:AbortSignal.timeout(7500)});
  if(response.status===204)return {status:204,data:null};
  const declared=Number(response.headers.get("content-length")||0);
  if(declared>65536)throw Error("oversize auth response");
  const content=await response.text();
  if(content.length>65536)throw Error("oversize auth response");
  let data:unknown;
  try{data=JSON.parse(content)}catch{throw Error("invalid auth response")}
  return {status:response.status,data};
}
async function getUser(config:AuthConfig,token:string):Promise<{status:number;data:unknown}> {
  return authFetch(config,"user",{accessToken:token});
}
export async function session(access?:string,refresh?:string):Promise<Session>{
  const config=authConfig();
  if(!config)return {status:503,reason:"AUTH_NOT_CONFIGURED"};
  if(!validToken(access)&&!validToken(refresh))return {status:401,reason:"NO_SESSION"};
  if(validToken(access)){
    try{
      const reply=await getUser(config,access);
      if(reply.status===200){
        if(!isUser(reply.data))return {status:503,reason:"UPSTREAM_UNAVAILABLE"};
        return allowedUser(reply.data) ? {status:200,email:reply.data.email}
          : {status:403,reason:"NOT_AUTHORIZED",clear:true};
      }
      if(reply.status!==401 && reply.status!==403)return {status:503,reason:"UPSTREAM_UNAVAILABLE"};
    }catch{return {status:503,reason:"UPSTREAM_UNAVAILABLE"}}
  }
  if(!validToken(refresh))return {status:401,reason:"SESSION_EXPIRED",clear:true};
  try {
    const reply=await authFetch(config,"token?grant_type=refresh_token",{method:"POST",body:{refresh_token:refresh}});
    if(reply.status!==200){
      // Supabase error codes, not ambiguous status/message strings, establish expiry.
      // https://supabase.com/docs/guides/auth/debugging/error-codes
      const data=reply.data as {error_code?:unknown;code?:unknown}|null;
      const code=data && typeof data==="object" ? data.error_code??data.code : null;
      const rejected=[400,401,403].includes(reply.status) &&
        ["refresh_token_not_found","refresh_token_already_used","session_not_found","session_expired","invalid_credentials"].includes(String(code));
      if(rejected)return {status:401,reason:"SESSION_EXPIRED",clear:true};
      if(reply.status===403 && code==="user_banned")return {status:403,reason:"NOT_AUTHORIZED",clear:true};
      return {status:503,reason:"UPSTREAM_UNAVAILABLE"};
    }
    if(!reply.data || typeof reply.data!=="object")return {status:503,reason:"UPSTREAM_UNAVAILABLE"};
    const tokens=reply.data as TokenResponse;
    if(!validToken(tokens.access_token)||!validToken(tokens.refresh_token))return {status:503,reason:"UPSTREAM_UNAVAILABLE"};
    const user=await getUser(config,tokens.access_token);
    if(user.status!==200){
      if(user.status===401 || user.status===403)return {status:403,reason:"NOT_AUTHORIZED",clear:true};
      return {status:503,reason:"UPSTREAM_UNAVAILABLE"};
    }
    if(!isUser(user.data))return {status:503,reason:"UPSTREAM_UNAVAILABLE"};
    if(!allowedUser(user.data))return {status:403,reason:"NOT_AUTHORIZED",clear:true};
    return {status:200,email:user.data.email,tokens};
  } catch {return {status:503,reason:"UPSTREAM_UNAVAILABLE"};}
}
function cookieSettings(maxAge:number,sameSite:"strict"|"lax") {
  return {path:"/",secure:true,httpOnly:true,sameSite,maxAge} as const;
}
export function setSessionCookies(response:NextResponse,tokens:TokenResponse) {
  if(!validToken(tokens.access_token)||!validToken(tokens.refresh_token))throw Error("Invalid upstream tokens");
  const seconds=Math.min(3600,Math.max(60,Number(tokens.expires_in)||3600));
  response.cookies.set(ACCESS_COOKIE,tokens.access_token,cookieSettings(seconds,"strict"));
  response.cookies.set(REFRESH_COOKIE,tokens.refresh_token,cookieSettings(604800,"strict"));
}
export function clearSessionCookies(response:NextResponse) {
  response.cookies.set(ACCESS_COOKIE,"",cookieSettings(0,"strict"));
  response.cookies.set(REFRESH_COOKIE,"",cookieSettings(0,"strict"));
}
export function setFlowCookie(response:NextResponse,verifier:string) {
  response.cookies.set(FLOW_COOKIE,verifier,cookieSettings(300,"lax"));
}
export function clearFlowCookie(response:NextResponse) {
  response.cookies.set(FLOW_COOKIE,"",cookieSettings(0,"lax"));
}
export function createChallenge():{verifier:string;challenge:string}{
  const verifier=randomBytes(48).toString("base64url");
  const challenge=createHash("sha256").update(verifier).digest("base64url");
  return {verifier,challenge};
}
export function isValidVerifier(value:unknown):value is string {
  return typeof value==="string" && /^[A-Za-z0-9_-]{60,130}$/.test(value);
}
export function sameSiteLogin(request:NextRequest) {
  const site=request.headers.get("sec-fetch-site"),mode=request.headers.get("sec-fetch-mode");
  return (site===null||site==="same-origin"||site==="none")&&(mode===null||mode==="navigate");
}
export function noStore<T extends NextResponse>(response:T):T {
  response.headers.set("Cache-Control","private, no-store, max-age=0");
  response.headers.set("Vary","Cookie");
  response.headers.set("Referrer-Policy","no-referrer");
  return response;
}
