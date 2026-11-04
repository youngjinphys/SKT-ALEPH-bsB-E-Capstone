import Link from "next/link";
export default function NotFound(){return <main className="error-page"><h1>요청한 페이지를 찾을 수 없습니다.</h1><p>보안 실습과 발표 페이지로 이동할 수 있습니다.</p><Link href="/">홈으로 돌아가기 ↗</Link></main>}
