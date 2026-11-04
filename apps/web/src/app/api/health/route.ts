import {NextResponse} from "next/server";
import {authConfig,noStore} from "@/lib/auth";
export const dynamic="force-dynamic";
export function GET(){
  const configured=Boolean(authConfig());
  return noStore(NextResponse.json({status:configured?"configured":"unavailable"},{status:configured?200:503}));
}
