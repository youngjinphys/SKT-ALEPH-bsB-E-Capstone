/** Presentation capacity uses the visible viewport minus safe-area root padding. */
export function classifyMobilePresentation({height,paddingTop=0,paddingBottom=0,scale=1,narrow}:{height:number;paddingTop?:number;paddingBottom?:number;scale?:number;narrow:boolean}){
 const nonnegative=(value:number)=>Number.isFinite(value)?Math.max(0,value):0;
 const usableHeight=Math.max(0,nonnegative(height)-nonnegative(paddingTop)-nonnegative(paddingBottom));
 const unzoomed=!Number.isFinite(scale)||scale<=1;
 const fits=usableHeight>=700&&unzoomed;
 return {mobile:narrow||usableHeight<700||!unzoomed,fits,shortBudget:fits&&usableHeight<840,tightBudget:fits&&usableHeight<740,usableHeight,unzoomed};
}
