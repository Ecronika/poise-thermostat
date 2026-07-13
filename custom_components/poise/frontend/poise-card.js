/* poise-card 0.170.0 — bundled, served by the Poise integration (ADR-0040) */
var Z=globalThis,J=Z.ShadowRoot&&(Z.ShadyCSS===void 0||Z.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,he=Symbol(),Me=new WeakMap,U=class{constructor(e,t,o){if(this._$cssResult$=!0,o!==he)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o,t=this.t;if(J&&e===void 0){let o=t!==void 0&&t.length===1;o&&(e=Me.get(t)),e===void 0&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),o&&Me.set(t,e))}return e}toString(){return this.cssText}},Le=n=>new U(typeof n=="string"?n:n+"",void 0,he),N=(n,...e)=>{let t=n.length===1?n[0]:e.reduce((o,r,i)=>o+(s=>{if(s._$cssResult$===!0)return s.cssText;if(typeof s=="number")return s;throw Error("Value passed to 'css' function must be a 'css' function result: "+s+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(r)+n[i+1],n[0]);return new U(t,n,he)},He=(n,e)=>{if(J)n.adoptedStyleSheets=e.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(let t of e){let o=document.createElement("style"),r=Z.litNonce;r!==void 0&&o.setAttribute("nonce",r),o.textContent=t.cssText,n.appendChild(o)}},me=J?n=>n:n=>n instanceof CSSStyleSheet?(e=>{let t="";for(let o of e.cssRules)t+=o.cssText;return Le(t)})(n):n;var{is:bt,defineProperty:yt,getOwnPropertyDescriptor:vt,getOwnPropertyNames:xt,getOwnPropertySymbols:$t,getPrototypeOf:wt}=Object,Q=globalThis,Re=Q.trustedTypes,Ct=Re?Re.emptyScript:"",At=Q.reactiveElementPolyfillSupport,F=(n,e)=>n,fe={toAttribute(n,e){switch(e){case Boolean:n=n?Ct:null;break;case Object:case Array:n=n==null?n:JSON.stringify(n)}return n},fromAttribute(n,e){let t=n;switch(e){case Boolean:t=n!==null;break;case Number:t=n===null?null:Number(n);break;case Object:case Array:try{t=JSON.parse(n)}catch{t=null}}return t}},De=(n,e)=>!bt(n,e),Te={attribute:!0,type:String,converter:fe,reflect:!1,useDefault:!1,hasChanged:De};Symbol.metadata??=Symbol("metadata"),Q.litPropertyMetadata??=new WeakMap;var w=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=Te){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(e,t),!t.noAccessor){let o=Symbol(),r=this.getPropertyDescriptor(e,o,t);r!==void 0&&yt(this.prototype,e,r)}}static getPropertyDescriptor(e,t,o){let{get:r,set:i}=vt(this.prototype,e)??{get(){return this[t]},set(s){this[t]=s}};return{get:r,set(s){let l=r?.call(this);i?.call(this,s),this.requestUpdate(e,l,o)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??Te}static _$Ei(){if(this.hasOwnProperty(F("elementProperties")))return;let e=wt(this);e.finalize(),e.l!==void 0&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(F("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(F("properties"))){let t=this.properties,o=[...xt(t),...$t(t)];for(let r of o)this.createProperty(r,t[r])}let e=this[Symbol.metadata];if(e!==null){let t=litPropertyMetadata.get(e);if(t!==void 0)for(let[o,r]of t)this.elementProperties.set(o,r)}this._$Eh=new Map;for(let[t,o]of this.elementProperties){let r=this._$Eu(t,o);r!==void 0&&this._$Eh.set(r,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){let t=[];if(Array.isArray(e)){let o=new Set(e.flat(1/0).reverse());for(let r of o)t.unshift(me(r))}else e!==void 0&&t.push(me(e));return t}static _$Eu(e,t){let o=t.attribute;return o===!1?void 0:typeof o=="string"?o:typeof e=="string"?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),this.renderRoot!==void 0&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){let e=new Map,t=this.constructor.elementProperties;for(let o of t.keys())this.hasOwnProperty(o)&&(e.set(o,this[o]),delete this[o]);e.size>0&&(this._$Ep=e)}createRenderRoot(){let e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return He(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,o){this._$AK(e,o)}_$ET(e,t){let o=this.constructor.elementProperties.get(e),r=this.constructor._$Eu(e,o);if(r!==void 0&&o.reflect===!0){let i=(o.converter?.toAttribute!==void 0?o.converter:fe).toAttribute(t,o.type);this._$Em=e,i==null?this.removeAttribute(r):this.setAttribute(r,i),this._$Em=null}}_$AK(e,t){let o=this.constructor,r=o._$Eh.get(e);if(r!==void 0&&this._$Em!==r){let i=o.getPropertyOptions(r),s=typeof i.converter=="function"?{fromAttribute:i.converter}:i.converter?.fromAttribute!==void 0?i.converter:fe;this._$Em=r;let l=s.fromAttribute(t,i.type);this[r]=l??this._$Ej?.get(r)??l,this._$Em=null}}requestUpdate(e,t,o,r=!1,i){if(e!==void 0){let s=this.constructor;if(r===!1&&(i=this[e]),o??=s.getPropertyOptions(e),!((o.hasChanged??De)(i,t)||o.useDefault&&o.reflect&&i===this._$Ej?.get(e)&&!this.hasAttribute(s._$Eu(e,o))))return;this.C(e,t,o)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(e,t,{useDefault:o,reflect:r,wrapped:i},s){o&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,s??t??this[e]),i!==!0||s!==void 0)||(this._$AL.has(e)||(this.hasUpdated||o||(t=void 0),this._$AL.set(e,t)),r===!0&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}let e=this.scheduleUpdate();return e!=null&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[r,i]of this._$Ep)this[r]=i;this._$Ep=void 0}let o=this.constructor.elementProperties;if(o.size>0)for(let[r,i]of o){let{wrapped:s}=i,l=this[r];s!==!0||this._$AL.has(r)||l===void 0||this.C(r,void 0,i,l)}}let e=!1,t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(o=>o.hostUpdate?.()),this.update(t)):this._$EM()}catch(o){throw e=!1,this._$EM(),o}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(e){}firstUpdated(e){}};w.elementStyles=[],w.shadowRootOptions={mode:"open"},w[F("elementProperties")]=new Map,w[F("finalized")]=new Map,At?.({ReactiveElement:w}),(Q.reactiveElementVersions??=[]).push("2.1.2");var $e=globalThis,Oe=n=>n,ee=$e.trustedTypes,Ie=ee?ee.createPolicy("lit-html",{createHTML:n=>n}):void 0,Be="$lit$",C=`lit$${Math.random().toFixed(9).slice(2)}$`,Ke="?"+C,St=`<${Ke}>`,E=document,V=()=>E.createComment(""),B=n=>n===null||typeof n!="object"&&typeof n!="function",we=Array.isArray,kt=n=>we(n)||typeof n?.[Symbol.iterator]=="function",_e=`[ 	
\f\r]`,z=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Ue=/-->/g,Ne=/>/g,S=RegExp(`>|${_e}(?:([^\\s"'>=/]+)(${_e}*=${_e}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),Fe=/'/g,ze=/"/g,je=/^(?:script|style|textarea|title)$/i,Ce=n=>(e,...t)=>({_$litType$:n,strings:e,values:t}),h=Ce(1),qe=Ce(2),hn=Ce(3),P=Symbol.for("lit-noChange"),u=Symbol.for("lit-nothing"),Ve=new WeakMap,k=E.createTreeWalker(E,129);function We(n,e){if(!we(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return Ie!==void 0?Ie.createHTML(e):e}var Et=(n,e)=>{let t=n.length-1,o=[],r,i=e===2?"<svg>":e===3?"<math>":"",s=z;for(let l=0;l<t;l++){let a=n[l],d,f,m=-1,g=0;for(;g<a.length&&(s.lastIndex=g,f=s.exec(a),f!==null);)g=s.lastIndex,s===z?f[1]==="!--"?s=Ue:f[1]!==void 0?s=Ne:f[2]!==void 0?(je.test(f[2])&&(r=RegExp("</"+f[2],"g")),s=S):f[3]!==void 0&&(s=S):s===S?f[0]===">"?(s=r??z,m=-1):f[1]===void 0?m=-2:(m=s.lastIndex-f[2].length,d=f[1],s=f[3]===void 0?S:f[3]==='"'?ze:Fe):s===ze||s===Fe?s=S:s===Ue||s===Ne?s=z:(s=S,r=void 0);let b=s===S&&n[l+1].startsWith("/>")?" ":"";i+=s===z?a+St:m>=0?(o.push(d),a.slice(0,m)+Be+a.slice(m)+C+b):a+C+(m===-2?l:b)}return[We(n,i+(n[t]||"<?>")+(e===2?"</svg>":e===3?"</math>":"")),o]},K=class n{constructor({strings:e,_$litType$:t},o){let r;this.parts=[];let i=0,s=0,l=e.length-1,a=this.parts,[d,f]=Et(e,t);if(this.el=n.createElement(d,o),k.currentNode=this.el.content,t===2||t===3){let m=this.el.content.firstChild;m.replaceWith(...m.childNodes)}for(;(r=k.nextNode())!==null&&a.length<l;){if(r.nodeType===1){if(r.hasAttributes())for(let m of r.getAttributeNames())if(m.endsWith(Be)){let g=f[s++],b=r.getAttribute(m).split(C),$=/([.?@])?(.*)/.exec(g);a.push({type:1,index:i,name:$[2],strings:b,ctor:$[1]==="."?be:$[1]==="?"?ye:$[1]==="@"?ve:R}),r.removeAttribute(m)}else m.startsWith(C)&&(a.push({type:6,index:i}),r.removeAttribute(m));if(je.test(r.tagName)){let m=r.textContent.split(C),g=m.length-1;if(g>0){r.textContent=ee?ee.emptyScript:"";for(let b=0;b<g;b++)r.append(m[b],V()),k.nextNode(),a.push({type:2,index:++i});r.append(m[g],V())}}}else if(r.nodeType===8)if(r.data===Ke)a.push({type:2,index:i});else{let m=-1;for(;(m=r.data.indexOf(C,m+1))!==-1;)a.push({type:7,index:i}),m+=C.length-1}i++}}static createElement(e,t){let o=E.createElement("template");return o.innerHTML=e,o}};function H(n,e,t=n,o){if(e===P)return e;let r=o!==void 0?t._$Co?.[o]:t._$Cl,i=B(e)?void 0:e._$litDirective$;return r?.constructor!==i&&(r?._$AO?.(!1),i===void 0?r=void 0:(r=new i(n),r._$AT(n,t,o)),o!==void 0?(t._$Co??=[])[o]=r:t._$Cl=r),r!==void 0&&(e=H(n,r._$AS(n,e.values),r,o)),e}var ge=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){let{el:{content:t},parts:o}=this._$AD,r=(e?.creationScope??E).importNode(t,!0);k.currentNode=r;let i=k.nextNode(),s=0,l=0,a=o[0];for(;a!==void 0;){if(s===a.index){let d;a.type===2?d=new j(i,i.nextSibling,this,e):a.type===1?d=new a.ctor(i,a.name,a.strings,this,e):a.type===6&&(d=new xe(i,this,e)),this._$AV.push(d),a=o[++l]}s!==a?.index&&(i=k.nextNode(),s++)}return k.currentNode=E,r}p(e){let t=0;for(let o of this._$AV)o!==void 0&&(o.strings!==void 0?(o._$AI(e,o,t),t+=o.strings.length-2):o._$AI(e[t])),t++}},j=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,o,r){this.type=2,this._$AH=u,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=o,this.options=r,this._$Cv=r?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,t=this._$AM;return t!==void 0&&e?.nodeType===11&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=H(this,e,t),B(e)?e===u||e==null||e===""?(this._$AH!==u&&this._$AR(),this._$AH=u):e!==this._$AH&&e!==P&&this._(e):e._$litType$!==void 0?this.$(e):e.nodeType!==void 0?this.T(e):kt(e)?this.k(e):this._(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==u&&B(this._$AH)?this._$AA.nextSibling.data=e:this.T(E.createTextNode(e)),this._$AH=e}$(e){let{values:t,_$litType$:o}=e,r=typeof o=="number"?this._$AC(e):(o.el===void 0&&(o.el=K.createElement(We(o.h,o.h[0]),this.options)),o);if(this._$AH?._$AD===r)this._$AH.p(t);else{let i=new ge(r,this),s=i.u(this.options);i.p(t),this.T(s),this._$AH=i}}_$AC(e){let t=Ve.get(e.strings);return t===void 0&&Ve.set(e.strings,t=new K(e)),t}k(e){we(this._$AH)||(this._$AH=[],this._$AR());let t=this._$AH,o,r=0;for(let i of e)r===t.length?t.push(o=new n(this.O(V()),this.O(V()),this,this.options)):o=t[r],o._$AI(i),r++;r<t.length&&(this._$AR(o&&o._$AB.nextSibling,r),t.length=r)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);e!==this._$AB;){let o=Oe(e).nextSibling;Oe(e).remove(),e=o}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},R=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,o,r,i){this.type=1,this._$AH=u,this._$AN=void 0,this.element=e,this.name=t,this._$AM=r,this.options=i,o.length>2||o[0]!==""||o[1]!==""?(this._$AH=Array(o.length-1).fill(new String),this.strings=o):this._$AH=u}_$AI(e,t=this,o,r){let i=this.strings,s=!1;if(i===void 0)e=H(this,e,t,0),s=!B(e)||e!==this._$AH&&e!==P,s&&(this._$AH=e);else{let l=e,a,d;for(e=i[0],a=0;a<i.length-1;a++)d=H(this,l[o+a],t,a),d===P&&(d=this._$AH[a]),s||=!B(d)||d!==this._$AH[a],d===u?e=u:e!==u&&(e+=(d??"")+i[a+1]),this._$AH[a]=d}s&&!r&&this.j(e)}j(e){e===u?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??"")}},be=class extends R{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===u?void 0:e}},ye=class extends R{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==u)}},ve=class extends R{constructor(e,t,o,r,i){super(e,t,o,r,i),this.type=5}_$AI(e,t=this){if((e=H(this,e,t,0)??u)===P)return;let o=this._$AH,r=e===u&&o!==u||e.capture!==o.capture||e.once!==o.once||e.passive!==o.passive,i=e!==u&&(o===u||r);r&&this.element.removeEventListener(this.name,this,o),i&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}},xe=class{constructor(e,t,o){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=o}get _$AU(){return this._$AM._$AU}_$AI(e){H(this,e)}};var Pt=$e.litHtmlPolyfillSupport;Pt?.(K,j),($e.litHtmlVersions??=[]).push("3.3.3");var Ge=(n,e,t)=>{let o=t?.renderBefore??e,r=o._$litPart$;if(r===void 0){let i=t?.renderBefore??null;o._$litPart$=r=new j(e.insertBefore(V(),i),i,void 0,t??{})}return r._$AI(n),r};var Ae=globalThis,x=class extends w{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=Ge(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return P}};x._$litElement$=!0,x.finalized=!0,Ae.litElementHydrateSupport?.({LitElement:x});var Mt=Ae.litElementPolyfillSupport;Mt?.({LitElement:x});(Ae.litElementVersions??=[]).push("4.2.2");function Lt(n,e,t){return Math.min(Math.max(n,e),t)}function te(n,e,t){return t<=e?.5:Lt((n-e)/(t-e),0,1)}function Ht(n,e,t){if(n==null)return"unknown";if(n<e)return"below";if(n>t)return"above";let o=t-e;if(o<=0)return"in_band";let r=(n-e)/o;return r<.25?"cool_edge":r>.75?"warm_edge":"in_band"}function Xe(n){let{operative:e,setpoint:t,low:o,high:r}=n;if(o==null||r==null||r<=o)return null;let i=o-1.5,s=r+1.5;return{low:o,high:r,span:r-o,operative:e,setpoint:t,category:n.category??"",verdict:Ht(e,o,r),axisLow:i,axisHigh:s,lowFrac:te(o,i,s),highFrac:te(r,i,s),operativeFrac:e==null?null:te(e,i,s),setpointFrac:t==null?null:te(t,i,s)}}var Ye={ok:"var(--success-color, #43a047)",warn:"var(--warning-color, #fb8c00)",alert:"var(--error-color, #e53935)",unknown:"var(--disabled-text-color, #9e9e9e)"};function q(n){return Ye[n]??Ye.unknown}var Rt=[1e3,2e3],Tt=[30,40,60,65],Dt=[26,30],Ot=420,It=[800,1350];function _(n){return typeof n=="number"&&Number.isFinite(n)}function ne(n,e){return n&&n.length>=2&&_(n[0])&&_(n[1])&&n[0]<n[1]?[n[0],n[1]]:[e[0],e[1]]}function Ut(n,e){if(n&&n.length>=4&&n.slice(0,4).every(_)){let[t,o,r,i]=n;if(t<=o&&o<=r&&r<=i)return[t,o,r,i]}return[e[0],e[1],e[2],e[3]]}function Nt(n){if(n?.scheme==="en16798"){let e=_(n.outdoor)?n.outdoor:Ot,t=ne(n.enRise,It);return[e+t[0],e+t[1]]}return ne(n?.thresholds,Rt)}function Ft(n,e){if(!_(n))return"unknown";let[t,o]=Nt(e);return n>=o?"alert":n>=t?"warn":"ok"}function zt(n,e){if(!_(n))return"unknown";let[t,o,r,i]=Ut(e,Tt);return n<t||n>=i?"alert":n<o||n>r?"warn":"ok"}function Vt(n){switch(n){case"in_band":return"ok";case"cool_edge":case"warm_edge":return"warn";case"below":case"above":return"alert";default:return"unknown"}}function Bt(n,e){if(!_(n))return"unknown";let[t,o]=ne(e,Dt);return n>o?"alert":n>t?"warn":"ok"}var Kt=[10,15];function jt(n){return 100-95*Math.exp(-(.03353*n**4+.2179*n**2))}function qt(n,e,t){let[o,r]=ne(t,Kt),i=_(e)?e:_(n)?jt(n):null;return i==null?"unknown":i>=r?"alert":i>=o?"warn":"ok"}var Wt=[.5,1],Gt=[3,6],Xt=[85,60];function Je(n){return n<=1?n*100:n}var Ze={unknown:-1,ok:0,warn:1,alert:2};function Yt(n){let e=[];if(_(n.deviationK)){let[t,o]=Wt;e.push(n.deviationK>=o?"alert":n.deviationK>=t?"warn":"ok")}if(_(n.cyclesPerH)){let[t,o]=Gt;e.push(n.cyclesPerH>=o?"alert":n.cyclesPerH>=t?"warn":"ok")}if(_(n.timeInBand)){let t=Je(n.timeInBand),[o,r]=Xt;e.push(t<r?"alert":t<o?"warn":"ok")}return e.length?e.reduce((t,o)=>Ze[o]>Ze[t]?o:t,"ok"):"unknown"}function Qe(n,e){let t=[],o=e?.temperature_scale==="asr_office"?Bt(n.temperature,e.asr_thresholds):Vt(n.comfortVerdict??null);if(t.push({key:"temperature",value:n.temperature,unit:"\xB0C",level:o,color:q(o)}),_(n.humidity)){let i=zt(n.humidity,e?.humidity_thresholds);t.push({key:"humidity",value:n.humidity,unit:"%",level:i,color:q(i)})}if(_(n.co2)){let i=Ft(n.co2,{scheme:e?.co2_scheme,thresholds:e?.co2_thresholds,outdoor:e?.outdoor_co2});t.push({key:"co2",value:n.co2,unit:"ppm",level:i,color:q(i)})}if(_(n.pmv)||_(n.ppd)){let i=qt(n.pmv??null,n.ppd??null);t.push({key:"pmv",value:_(n.ppd)?n.ppd:null,unit:"%",level:i,color:q(i)})}let r=n.ca;if(r&&(_(r.deviationK)||_(r.timeInBand)||_(r.cyclesPerH))){let i=Yt(r);t.push({key:"ca",value:_(r.timeInBand)?Je(r.timeInBand):null,unit:"%",level:i,color:q(i)})}return t}var Se=["hvac","window","temperature","humidity","co2","ca"],Zt=[12,24,48];function et(n,e,t){return typeof n=="string"&&e.includes(n)?n:t}function T(n,e){return typeof n=="boolean"?n:e}function Jt(n){return n===!1?new Set:n==null||n===!0?new Set(Se):Array.isArray(n)?new Set(n.filter(e=>Se.includes(e))):new Set(Se)}function Qt(n){if(n===!1)return{show:!1,hours:24};if(n===!0||n==null)return{show:!0,hours:24};let e=typeof n.hours=="number"?n.hours:Number(n.hours),t=Zt.includes(e)?e:24;return{show:T(n.show,!0),hours:t}}function tt(n){let e=n.sections??{},t=n.density?et(n.density,["comfortable","compact"],"comfortable"):n.compact?"compact":"comfortable";return{entity:n.entity,density:t,controls:et(n.controls,["dial","buttons","none"],"dial"),history:Qt(n.history),chips:Jt(e.chips),shadowPill:T(e.shadow_pill,T(n.show_shadow,!0)),learning:T(e.learning,!0),pmv:T(e.pmv,!0),presets:T(e.presets,!0),temperature_scale:n.temperature_scale,humidity_thresholds:n.humidity_thresholds,co2_scheme:n.co2_scheme,co2_thresholds:n.co2_thresholds}}var nt={in_band:"In comfort band",cool_edge:"Cool edge of band",warm_edge:"Warm edge of band",below:"Below comfort band",above:"Above comfort band",unknown:"No reading",preheating:"Pre-heating",coasting:"Coasting",window:"Window open",window_auto:"Window (auto)",bypass:"Window detection off",eco:"Eco",comfort:"Comfort",boost:"Boost",away:"Away",failure:"Heating failure",learning:"Learning",shadow:"Shadow active",setpoint:"Setpoint",no_entity:"Select a Poise thermostat entity.",min_left:"min",no_system:"Select the Poise System sensor.",sys_title:"Poise System",demand_on:"Boiler demand",demand_off:"No demand",frost:"Frost override",zones:"zones",heating_n:"heating",flow:"Flow",shed:"shed",shadow_would:"would",update_msg:"New Poise card version available \u2014 reload to update.",reload:"Reload",details:"Show details",temperature:"Temperature",humidity:"Humidity",co2:"CO\u2082",pmv:"Comfort",ca:"Regulation",override_clamped:"Setpoint clamped",manual:"Manual",resume_schedule:"Resume schedule",valid_until:"valid until",instead_of:"instead of",norm_limit:"norm limit",permanent:"permanent",operative:"operative",air:"air",cools:"cooling",heats:"heating",dries:"drying",compressor_guard:"Compressor guard",mould:"Mould limit",presets:"Presets",air_quality:"Room condition",air_ok:"OK",air_warn:"Elevated",air_alert:"Critical"},en={in_band:"Im Komfortband",cool_edge:"Untere Bandkante",warm_edge:"Obere Bandkante",below:"Unter dem Komfortband",above:"\xDCber dem Komfortband",unknown:"Kein Messwert",preheating:"Vorheizen",coasting:"Auslaufen",window:"Fenster offen",window_auto:"Fenster (auto)",bypass:"Fenster-Erkennung aus",eco:"Eco",comfort:"Komfort",boost:"Boost",away:"Abwesend",failure:"Heizausfall",learning:"Lernt",shadow:"Shadow aktiv",setpoint:"Sollwert",no_entity:"Bitte eine Poise-Thermostat-Entit\xE4t w\xE4hlen.",min_left:"Min",no_system:"Bitte den Poise-System-Sensor w\xE4hlen.",sys_title:"Poise System",demand_on:"Kesselbedarf",demand_off:"Kein Bedarf",frost:"Frost-Override",zones:"Zonen",heating_n:"heizen",flow:"Vorlauf",shed:"abgeworfen",shadow_would:"w\xFCrde",update_msg:"Neue Poise-Karten-Version verf\xFCgbar \u2014 zum Aktualisieren neu laden.",reload:"Neu laden",details:"Details anzeigen",temperature:"Temperatur",humidity:"Feuchte",co2:"CO\u2082",pmv:"Behaglichkeit",ca:"Regelg\xFCte",override_clamped:"Sollwert geklemmt",manual:"Manuell",resume_schedule:"Zeitplan fortsetzen",valid_until:"gilt bis",instead_of:"statt",norm_limit:"Normgrenze",permanent:"dauerhaft",operative:"operativ",air:"Luft",cools:"k\xFChlt",heats:"heizt",dries:"entfeuchtet",compressor_guard:"Verdichterschutz",mould:"Schimmelgrenze",presets:"Voreinstellungen",air_quality:"Raumzustand",air_ok:"OK",air_warn:"Erh\xF6ht",air_alert:"Kritisch"};function c(n,e){return((n??"en").toLowerCase().startsWith("de")?en:nt)[e]??nt[e]??e}var tn=[{value:"hvac",label:"HVAC status"},{value:"window",label:"Window"},{value:"temperature",label:"Temperature"},{value:"humidity",label:"Humidity"},{value:"co2",label:"CO\u2082"},{value:"ca",label:"Regulation (CA)"}],nn=[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"climate"}}},{name:"density",selector:{select:{mode:"dropdown",options:[{value:"comfortable",label:"Comfortable"},{value:"compact",label:"Compact"}]}}},{name:"controls",selector:{select:{mode:"dropdown",options:[{value:"dial",label:"Dial (drag)"},{value:"buttons",label:"Buttons (+/\u2212)"},{value:"none",label:"Display only"}]}}},{type:"expandable",name:"history",title:"History",schema:[{name:"show",selector:{boolean:{}}},{name:"hours",selector:{select:{mode:"dropdown",options:[{value:12,label:"12 h"},{value:24,label:"24 h"},{value:48,label:"48 h"}]}}}]},{type:"expandable",name:"sections",title:"Sections",schema:[{name:"chips",selector:{select:{multiple:!0,options:tn}}},{name:"pmv",selector:{boolean:{}}},{name:"presets",selector:{boolean:{}}},{name:"shadow_pill",selector:{boolean:{}}},{name:"learning",selector:{boolean:{}}}]},{type:"expandable",name:"",title:"Advanced",flatten:!0,schema:[{name:"temperature_scale",selector:{select:{mode:"dropdown",options:[{value:"comfort",label:"Comfort band"},{value:"asr_office",label:"ASR office (\u226426 \xB0C)"}]}}},{name:"co2_scheme",selector:{select:{mode:"dropdown",options:[{value:"uba",label:"UBA (absolute)"},{value:"en16798",label:"EN 16798 (outdoor offset)"}]}}}]}],on={entity:"Entity",density:"Density",controls:"Controls",history:"History",sections:"Sections",show:"Show graph",hours:"Time span",chips:"Condition chips",pmv:"Comfort (PMV) lamp",presets:"Preset buttons",shadow_pill:"Shadow pill",learning:"Learning bar",temperature_scale:"Temperature scale",co2_scheme:"CO\u2082 scale"},oe=class extends x{setConfig(e){this._config=e}shouldUpdate(e){return e.has("hass")||e.has("_config")}_changed(e){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e.detail.value}}))}render(){return!this.hass||!this._config?h``:h`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${nn}
      .computeLabel=${e=>on[e.name]??e.name}
      @value-changed=${this._changed}
    ></ha-form>`}};oe.properties={hass:{},_config:{state:!0}};customElements.get("poise-card-editor")||customElements.define("poise-card-editor",oe);var ot="0.170.0",rt=!1;function rn(){let n=()=>location.reload();"caches"in window?caches.keys().then(e=>Promise.all(e.map(t=>caches.delete(t)))).then(n,n):n()}async function re(n,e){if(!(rt||!e?.connection)){rt=!0;try{let t=await e.connection.sendMessagePromise({type:"poise/card_version"});if(t?.version&&t.version!==ot){let o=e.locale?.language;n.dispatchEvent(new CustomEvent("hass-notification",{detail:{message:`${c(o,"update_msg")} (${ot} \u2192 ${t.version})`,duration:-1,dismissable:!0,action:{text:c(o,"reload"),action:rn}},bubbles:!0,composed:!0}))}}catch{}}}function W(n){let e=typeof n=="string"?parseFloat(n):n;return typeof e=="number"&&!Number.isNaN(e)?e:null}var G=class extends x{static getConfigElement(){return document.createElement("poise-system-card-editor")}static getStubConfig(e){return{type:"custom:poise-system-card",entity:Object.keys(e.states).find(o=>o.startsWith("binary_sensor.")&&e.states[o].attributes.zone_count!==void 0)??""}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config=e}getCardSize(){return 2}getGridOptions(){return{columns:12,rows:"auto",min_columns:4,min_rows:4}}updated(){this.hass&&re(this,this.hass)}shouldUpdate(e){if(e.has("_config"))return!0;let t=e.get("hass");return!t||!this._config?.entity?!0:t.states[this._config.entity]!==this.hass.states[this._config.entity]}_moreInfo(){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_onActivateKey(e){(e.key==="Enter"||e.key===" ")&&(e.preventDefault(),this._moreInfo())}render(){let e=this.hass?.locale?.language,t=this._config?.entity,o=t?this.hass.states[t]:void 0;if(!o)return h`<ha-card
        ><div class="empty">${c(e,"no_system")}</div></ha-card
      >`;let r=o.attributes,i=o.state==="on",s=W(r.flow_target),l=W(r.shed_count)??0,a=r.source_grants??{},d=Object.keys(a);return h`<ha-card .header=${c(e,"sys_title")}>
      <div
        class="wrap"
        role="button"
        tabindex="0"
        aria-label=${c(e,"details")}
        @click=${this._moreInfo}
        @keydown=${this._onActivateKey}
      >
        <div class="state ${i?"on":""}">
          <ha-icon icon=${i?"mdi:fire":"mdi:fire-off"}></ha-icon>
          <span>${i?c(e,"demand_on"):c(e,"demand_off")}</span>
          ${r.frost_override?h`<em class="frost">${c(e,"frost")}</em>`:u}
        </div>
        <div class="stats">
          <div>
            <strong>${W(r.active_zones)??0}</strong
            ><span>${c(e,"heating_n")}</span>
          </div>
          <div>
            <strong
              >${W(r.controlling_zones)??0}/${W(r.zone_count)??0}</strong
            ><span>${c(e,"zones")}</span>
          </div>
          ${s!=null?h`<div>
                <strong>${s.toFixed(0)}°</strong><span>${c(e,"flow")}</span>
              </div>`:u}
          ${l>0?h`<div>
                <strong>${l}</strong><span>${c(e,"shed")}</span>
              </div>`:u}
        </div>
        ${d.length?h`<div class="grants">
              ${d.map(f=>h`<span class="chip">${f}: ${a[f]}</span>`)}
            </div>`:u}
      </div>
    </ha-card>`}};G.properties={hass:{},_config:{state:!0}},G.styles=N`
    .wrap { padding: 8px 16px 16px; cursor: pointer; }
    .wrap:focus { outline: none; }
    .wrap:focus-visible {
      outline: 2px solid var(--primary-color, #2196f3);
      outline-offset: -2px; border-radius: 10px;
    }
    .state { display: flex; align-items: center; gap: 8px; font-size: 18px; }
    .state ha-icon { --mdc-icon-size: 22px; color: var(--secondary-text-color); }
    .state.on ha-icon { color: var(--error-color, #d33); }
    .frost { font-style: normal; margin-left: auto; padding: 2px 8px; border-radius: 10px;
      font-size: 11px; background: var(--info-color, #2196f3); color: var(--text-primary-color, #fff); }
    .stats { display: flex; gap: 18px; margin-top: 10px; flex-wrap: wrap; }
    .stats strong { font-size: 20px; }
    .stats span { display: block; font-size: 11px; color: var(--secondary-text-color); }
    .grants { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    .chip { padding: 3px 8px; border-radius: 12px; font-size: 12px;
      background: var(--secondary-background-color); }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
  `;var ie=class extends x{setConfig(e){this._config=e}shouldUpdate(e){return e.has("hass")||e.has("_config")}_changed(e){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e.detail.value}}))}render(){return!this.hass||!this._config?h``:h`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${[{name:"entity",required:!0,selector:{entity:{integration:"poise",domain:"binary_sensor"}}}]}
      .computeLabel=${e=>e.name}
      @value-changed=${this._changed}
    ></ha-form>`}};ie.properties={hass:{},_config:{state:!0}};customElements.get("poise-system-card-editor")||customElements.define("poise-system-card-editor",ie);customElements.get("poise-system-card")||customElements.define("poise-system-card",G);window.customCards=window.customCards||[];window.customCards.push({type:"poise-system-card",name:"Poise System",preview:!0,description:"Multi-zone boiler demand, flow & load shedding for the Poise hub."});function it(n,e,t){return Math.min(Math.max(n,e),t)}function st(n,e,t,o=300,r=90,i=1){let s=[];for(let y of n)y.op!=null&&s.push(y.op),y.sp!=null&&s.push(y.sp);if(e!=null&&s.push(e),t!=null&&s.push(t),s.length===0||n.length===0)return null;let l=Math.min(...s)-i,a=Math.max(...s)+i,d=n[0].t,m=n[n.length-1].t-d||1,g=a-l||1,b=y=>(y-d)/m*o,$=y=>r-(y-l)/g*r,X=y=>n.filter(M=>y(M)!=null).map(M=>`${b(M.t).toFixed(1)},${$(y(M)).toFixed(1)}`).join(" ");return{width:o,height:r,opPath:X(y=>y.op),spPath:X(y=>y.sp),bandTop:t==null?0:it($(t),0,r),bandBottom:e==null?r:it($(e),0,r),vMin:l,vMax:a}}var v={min:16,max:28,start:135,sweep:270};function at(n,e,t){return Math.min(Math.max(n,e),t)}function D(n,e=v){let t=at((n-e.min)/(e.max-e.min),0,1);return e.start+t*e.sweep}function sn(n,e=v){let t=n;for(;t<e.start;)t+=360;for(;t>=e.start+360;)t-=360;if(t<=e.start+e.sweep)return t;let o=t-(e.start+e.sweep);return e.start+360-t<o?e.start:e.start+e.sweep}function an(n,e=v){let o=(sn(n,e)-e.start)/e.sweep;return e.min+o*(e.max-e.min)}function A(n,e,t,o){let r=o*Math.PI/180;return{x:n+t*Math.cos(r),y:e+t*Math.sin(r)}}function ke(n,e,t,o,r){if(r<=o)return"";let i=A(n,e,t,o),s=A(n,e,t,r),l=r-o>180?1:0;return`M ${i.x.toFixed(2)} ${i.y.toFixed(2)} A ${t} ${t} 0 ${l} 1 ${s.x.toFixed(2)} ${s.y.toFixed(2)}`}function lt(n,e,t=v){let o=Math.atan2(e,n)*180/Math.PI;return o<0&&(o+=360),an(o,t)}function ct(n,e,t,o=v){let r;switch(n){case"ArrowUp":case"ArrowRight":r=e+t;break;case"ArrowDown":case"ArrowLeft":r=e-t;break;case"PageUp":r=e+t*5;break;case"PageDown":r=e-t*5;break;case"Home":r=o.min;break;case"End":r=o.max;break;default:return null}return Math.round(at(r,o.min,o.max)/t)*t}function Ee(n,e=Date.now()){if(typeof n!="string")return null;let t=Date.parse(n);return Number.isNaN(t)?null:Math.max(0,Math.round((t-e)/6e4))}function ut(n,e){if(typeof n!="string")return null;let t=Date.parse(n);return Number.isNaN(t)?null:new Date(t).toLocaleTimeString(e,{hour:"2-digit",minute:"2-digit"})}function O(n){let e=n.temperature,t=typeof e=="string"?parseFloat(e):e;return typeof t=="number"&&!Number.isNaN(t)?t:null}function ln(n,e){let t=typeof e=="string"?e.toLowerCase():"";return t==="cooling"?c(n,"cools"):t==="heating"?c(n,"heats"):t==="drying"?c(n,"dries"):null}function dt(n,e,t,o,r=Date.now(),i=null){let s=c(n,"manual"),l=ln(n,i);return t==="permanent"?{label:`${s} (${c(n,"permanent")})`,minutes:null,permanent:!0,direction:l}:{label:e!=null?`${s} ${e.toFixed(1)}\xB0`:s,minutes:Ee(o,r),permanent:!1,direction:l}}function pt(n,e,t=.3){return n==null||e==null?null:Math.abs(n-e)>=t?e:null}function ht(n,e,t){return e==null||t==null?c(n,"override_clamped"):`${e.toFixed(1)}\xB0 ${c(n,"instead_of")} ${t.toFixed(1)}\xB0 (${c(n,"norm_limit")})`}function mt(n,e,t){let o=e==null?"none":String(e).toLowerCase();return o==="none"||t?null:{key:o,label:c(n,o)||o}}function ft(n,e){n.callService("poise","resume_schedule",{entity_id:e})}function _t(n){return{eco:"mdi:leaf",boost:"mdi:rocket-launch",away:"mdi:home-export-outline",comfort:"mdi:sofa"}[n]??"mdi:tune"}function p(n){let e=typeof n=="string"?parseFloat(n):n;return typeof e=="number"&&!Number.isNaN(e)?e:null}var se=class extends x{constructor(){super(...arguments);this._history=[];this._histFor=null;this._dragging=!1;this._pending=null;this._dialCfg=v}static getConfigElement(){return document.createElement("poise-card-editor")}static getStubConfig(t){return{type:"custom:poise-card",entity:Object.keys(t.states).find(r=>r.startsWith("climate.")&&t.states[r].attributes.comfort_low!==void 0)??"",show_shadow:!0}}setConfig(t){if(!t)throw new Error("Invalid configuration");if(t.entity&&!t.entity.startsWith("climate."))throw new Error("Poise card: entity must be a climate entity");this._config={show_shadow:!0,...t},this._r=tt(this._config)}getCardSize(){return 4}getGridOptions(){return this._r?.density==="compact"?{columns:6,rows:"auto",min_columns:4,min_rows:6}:{columns:12,rows:"auto",min_columns:6,min_rows:9}}shouldUpdate(t){if(this._dragging||t.has("_config"))return!0;let o=t.get("hass");return!o||!this._config?.entity?!0:o.states[this._config.entity]!==this.hass.states[this._config.entity]}_setpoint(t){let o=this._config.entity;if(!o||!this.hass)return;let r=this.hass.states[o];if(!r)return;let i=p(r.attributes.target_temperature_step)??.5,s=this._pending??O(r.attributes)??21;this.hass.callService("climate","set_temperature",{entity_id:o,temperature:Math.round((s+t*i)*10)/10})}updated(){this.hass&&re(this,this.hass);let t=this._config?.entity;t&&this.hass&&this._r?.history.show&&this._histFor!==t&&(this._histFor=t,this._loadHistory(t))}async _loadHistory(t){if(!this.hass.connection)return;let o=this._r?.history.hours??24,r=new Date,i=new Date(r.getTime()-o*3600*1e3);try{let l=(await this.hass.connection.sendMessagePromise({type:"history/history_during_period",start_time:i.toISOString(),end_time:r.toISOString(),entity_ids:[t],minimal_response:!1,no_attributes:!1}))?.[t]??[],a={},d=[];for(let f of l){f.a&&(a={...a,...f.a});let m=(p(f.lu)??p(f.lc)??0)*1e3;d.push({t:m,op:p(a.operative_temperature)??p(a.current_temperature),sp:p(a.temperature)})}this._history=d,this.requestUpdate()}catch{}}_moreInfo(){this._config.entity&&this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_chart(t,o){let r=st(this._history,t,o,300,80);return r?h`<svg
      class="chart"
      viewBox="0 0 ${r.width} ${r.height}"
      preserveAspectRatio="none"
    >
      <rect
        x="0"
        y=${r.bandTop}
        width=${r.width}
        height=${Math.max(0,r.bandBottom-r.bandTop)}
        class="cband"
      ></rect>
      <polyline points=${r.spPath} class="csp"></polyline>
      <polyline points=${r.opPath} class="cop"></polyline>
    </svg>`:u}render(){let t=this.hass?.locale?.language,o=this._config?.entity,r=o?this.hass.states[o]:void 0;if(!r)return h`<ha-card
        ><div class="empty">${c(t,"no_entity")}</div></ha-card
      >`;let i=r.attributes,s=p(i.operative_temperature)??p(i.current_temperature),l=p(i.heat_sp)??p(i.temperature),a=Xe({operative:s,setpoint:l,low:p(i.comfort_low),high:p(i.comfort_high),category:i.category??null}),d=this._r;return h`<ha-card .header=${i.friendly_name??"Poise"}>
      <div class="wrap ${d.density==="compact"?"compact":""}">
        ${this._dial(i,t)}
        <div class="verdict">
          ${a?c(t,a.verdict):c(t,"unknown")}
          ${a?.category?h`<span class="cat">Kat. ${a.category}</span>`:u}
        </div>
        ${this._holdPill(i,t)}
        ${d.controls==="buttons"?this._control(this._pending??l,t):u}
        ${this._presets(i,t)}
        ${d.history.show?this._chart(p(i.comfort_low),p(i.comfort_high)):u}
        ${this._monitor(i,a,t)} ${this._chips(i,t)}
        ${this._learn(i,t)}
      </div>
    </ha-card>`}_dial(t,o){let r=p(t.operative_temperature)??p(t.current_temperature),i=pt(r,p(t.current_temperature)),s=O(t),l={min:p(t.min_temp)??v.min,max:p(t.max_temp)??v.max,start:v.start,sweep:v.sweep};this._dialCfg=l.max>l.min?l:v;let a=this._pending??s??r??this._dialCfg.min,d=p(t.comfort_low),f=p(t.comfort_high),m=100,g=100,b=80,$=ke(m,g,b,v.start,v.start+v.sweep),X=d!=null&&f!=null?ke(m,g,b,D(Math.min(d,f),this._dialCfg),D(Math.max(d,f),this._dialCfg)):"",y=String(t.hvac_action??""),M=y==="heating"?"heat":y==="cooling"?"cool":"",Pe=A(m,g,b,D(a,this._dialCfg)),ae=r!=null?A(m,g,b,D(r,this._dialCfg)):null,L=p(t.mould_floor),I=L!=null&&L>this._dialCfg.min&&L<this._dialCfg.max,le=I?D(L,this._dialCfg):0,ce=I?A(m,g,b-9,le):null,ue=I?A(m,g,b+9,le):null,de=I?A(m,g,b+17,le):null,pe=this._r.controls==="dial",Y=this._dragging?ut(t.override_expires_at,o):null,gt=`${a.toFixed(1)} \xB0C${Y?` \xB7 ${c(o,"valid_until")} ${Y}`:""}`;return h`<div class="dialwrap">
      <svg
        class="dial ${pe?"":"ro"}"
        viewBox="0 0 200 200"
        role=${pe?"slider":"img"}
        tabindex=${pe?0:-1}
        aria-label=${c(o,"setpoint")}
        aria-valuemin=${this._dialCfg.min}
        aria-valuemax=${this._dialCfg.max}
        aria-valuenow=${a}
        aria-valuetext=${gt}
        @keydown=${this._onKey}
        @pointerdown=${this._onDown}
        @pointermove=${this._onMove}
        @pointerup=${this._onUp}
        @pointercancel=${this._onUp}
      >
        <path class="track" d=${$}></path>
        <path class="bandarc" d=${X}></path>
        ${I&&ce&&ue&&de?qe`<line class="mould" x1=${ce.x.toFixed(1)} y1=${ce.y.toFixed(1)} x2=${ue.x.toFixed(1)} y2=${ue.y.toFixed(1)}><title>${c(o,"mould")} ${L.toFixed(1)}°</title></line><text class="mlbl" x=${de.x.toFixed(1)} y=${de.y.toFixed(1)}>${L.toFixed(0)}°</text>`:u}
        <circle
          class="opdot"
          cx=${(ae?.x??0).toFixed(1)}
          cy=${(ae?.y??0).toFixed(1)}
          r=${ae?5:0}
        ></circle>
        <circle class="handle ${M}" cx=${Pe.x.toFixed(1)} cy=${Pe.y.toFixed(1)} r="9"></circle>
      </svg>
      <div class="dialctr">
        <div
          class="ctrclick"
          role="button"
          tabindex="0"
          aria-label=${c(o,"details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          <div class="op" title=${c(o,"operative")}>${r!=null?r.toFixed(1):"\u2014"}<span>°C</span></div>
          ${i!=null?h`<div class="opair">${c(o,"operative")} · ${c(o,"air")} ${i.toFixed(1)}°</div>`:u}
          <div class="soll">${c(o,"setpoint")} <b>${a.toFixed(1)}°</b></div>
          ${Y?h`<div class="valid">${c(o,"valid_until")} ${Y}</div>`:u}
        </div>
      </div>
    </div>`}_fromPointer(t,o){let r=o.getBoundingClientRect();if(!r.width||!this._config.entity)return;let i=(t.clientX-r.left)/r.width*200-100,s=(t.clientY-r.top)/r.height*200-100,l=p(this.hass.states[this._config.entity]?.attributes.target_temperature_step)??.5;this._pending=Math.round(lt(i,s,this._dialCfg)/l)*l,this.requestUpdate()}_onDown(t){if(!this._config.entity||this._r.controls!=="dial")return;t.preventDefault();let o=t.currentTarget;o.setPointerCapture(t.pointerId),this._dragging=!0,this._fromPointer(t,o)}_onMove(t){this._dragging&&this._fromPointer(t,t.currentTarget)}_onUp(){if(!this._dragging)return;this._dragging=!1;let t=this._pending;this._pending=null,t!=null&&this._config.entity&&this.hass.callService("climate","set_temperature",{entity_id:this._config.entity,temperature:t}),this.requestUpdate()}_onKey(t){let o=this._config.entity;if(!o||this._r.controls!=="dial")return;let r=this.hass.states[o];if(!r)return;let i=p(r.attributes.target_temperature_step)??.5,s=this._pending??O(r.attributes)??this._dialCfg.min,l=ct(t.key,s,i,this._dialCfg);l!=null&&(t.preventDefault(),this.hass.callService("climate","set_temperature",{entity_id:o,temperature:l}))}_onActivateKey(t){(t.key==="Enter"||t.key===" ")&&(t.preventDefault(),this._moreInfo())}_control(t,o){return h`<div class="ctl">
      <ha-icon-button @click=${()=>this._setpoint(-1)} label="-">
        <ha-icon icon="mdi:minus"></ha-icon>
      </ha-icon-button>
      <div class="sp">
        <span>${c(o,"setpoint")}</span
        ><strong>${t!=null?t.toFixed(1):"\u2014"}°C</strong>
      </div>
      <ha-icon-button @click=${()=>this._setpoint(1)} label="+">
        <ha-icon icon="mdi:plus"></ha-icon>
      </ha-icon-button>
    </div>`}_setPreset(t){let o=this._config.entity;!o||!this.hass||this.hass.callService("climate","set_preset_mode",{entity_id:o,preset_mode:t})}_resumeSchedule(){let t=this._config.entity;!t||!this.hass||ft(this.hass,t)}_presets(t,o){if(!this._r.presets)return u;let r=t.preset_modes;if(!Array.isArray(r)||!r.length)return u;let i=t.preset_mode==null?null:String(t.preset_mode),s=Ee(t.boost_expires_at);return h`<div class="presets" role="group" aria-label=${c(o,"presets")}>
      ${r.map(l=>{let a=String(l),d=a.toLowerCase();return h`<button
          class="preset ${i===a?"on":""}"
          aria-pressed=${i===a?"true":"false"}
          @click=${()=>this._setPreset(a)}
        >
          <ha-icon icon=${_t(d)}></ha-icon>
          <span>${c(o,d)||a}</span>
          ${d==="boost"&&s!=null?h`<em>${s} ${c(o,"min_left")}</em>`:u}
        </button>`})}
    </div>`}_holdPill(t,o){if(!t.override_active)return u;let r=O(t),i=dt(o,r,t.override_policy,t.override_expires_at,Date.now(),t.hvac_action);return h`<div class="hold">
      <div class="chip hold-chip">
        <ha-icon icon="mdi:hand-back-right"></ha-icon><span>${i.label}</span>
        ${i.direction!=null?h`<em>· ${i.direction}</em>`:u}
        ${i.minutes!=null?h`<em>· ${i.minutes} ${c(o,"min_left")}</em>`:u}
      </div>
      <button
        class="resume"
        aria-label=${c(o,"resume_schedule")}
        title=${c(o,"resume_schedule")}
        @click=${this._resumeSchedule}
      >
        <ha-icon icon="mdi:close"></ha-icon>
      </button>
    </div>`}_chips(t,o){let r=this._r,i=[];if(r.chips.has("hvac")){t.preheating&&i.push(this._chip("mdi:fire-circle",c(o,"preheating"),t.minutes_to_comfort,o)),t.coasting&&i.push(this._chip("mdi:coffee",c(o,"coasting"),t.minutes_to_setback,o));let s=mt(o,t.preset,r.presets);s&&i.push(this._chip(_t(s.key),s.label)),t.heating_failure&&i.push(this._chip("mdi:alert",c(o,"failure"))),t.override_clamped&&i.push(this._chip("mdi:arrow-collapse-vertical",ht(o,O(t),p(t.override_requested)))),t.mode_nudge_blocked&&i.push(this._chip("mdi:timer-sand",`${c(o,"compressor_guard")}: ${t.mode_nudge_blocked}`));let l=t.binding_lower_cause;l&&l!=="en16798"&&i.push(this._chip("mdi:shield-alert",String(l)))}return r.chips.has("window")&&(t.window_open&&i.push(this._chip("mdi:window-open",c(o,t.window_auto_detected?"window_auto":"window"))),t.window_bypass&&i.push(this._chip("mdi:window-closed-variant",c(o,"bypass")))),i.length?h`<div
          class="chips"
          role="button"
          tabindex="0"
          aria-label=${c(o,"details")}
          @click=${this._moreInfo}
          @keydown=${this._onActivateKey}
        >
          ${i}
        </div>`:u}_chip(t,o,r,i){let s=p(r);return h`<div class="chip">
      <ha-icon icon=${t}></ha-icon><span>${o}</span>
      ${s!=null?h`<em>${Math.round(s)} ${c(i,"min_left")}</em>`:u}
    </div>`}_monitor(t,o,r){let i=Qe({temperature:p(t.operative_temperature)??p(t.current_temperature),comfortVerdict:o?.verdict??null,humidity:p(t.humidity)??p(t.current_humidity),co2:p(t.co2)??p(t.carbon_dioxide),pmv:p(t.pmv),ppd:p(t.ppd),ca:{deviationK:p(t.ca_deviation_k),timeInBand:p(t.ca_time_in_band),cyclesPerH:p(t.ca_cycles_per_h)}},{temperature_scale:this._config.temperature_scale,humidity_thresholds:this._config.humidity_thresholds,co2_scheme:this._config.co2_scheme,co2_thresholds:this._config.co2_thresholds,outdoor_co2:p(t.outdoor_co2)}),s=this._r,l=i.filter(a=>a.key==="pmv"?s.pmv:s.chips.has(a.key));return l.length?h`<div
      class="monitor"
      role="group"
      aria-label=${c(r,"air_quality")}
    >
      ${l.map(a=>this._lamp(a,r))}
    </div>`:u}_lamp(t,o){let r=c(o,t.key),i=c(o,t.level==="unknown"?"unknown":"air_"+t.level),s="\u2014";t.value!=null&&(s=t.key==="temperature"?t.value.toFixed(1):String(Math.round(t.value)));let l=`${r}: ${s} ${t.unit} \u2014 ${i}`;return h`<div class="lamp" title=${l} aria-label=${l}>
      <span class="dot" style="background:${t.color}"></span>
      <span class="lk">${r}</span>
      <span class="lv">${s}<small>${t.unit}</small></span>
    </div>`}_learn(t,o){let r=p(t.confidence),i=this._r.learning&&r!=null,s=this._r.shadowPill&&(t.mpc_active||t.tpi_active||t.pi_active);if(!i&&!s)return u;let l=p(t.pi_setpoint),a=p(t.mpc_setpoint),d=t.tpi_active?`TPI ${Math.round(p(t.tpi_valve_percent)??0)}%`:t.pi_active&&l!=null?`PI ${l.toFixed(1)}\xB0`:t.mpc_active&&a!=null?`MPC ${a.toFixed(1)}\xB0`:"";return h`<div class="learn">
      ${i?h`<div class="bar">
            <i style="width:${((r??0)*100).toFixed(0)}%"></i>
          </div>
          <span>${c(o,"learning")} ${((r??0)*100).toFixed(0)}%</span>`:u}
      ${s?h`<div class="pill">
            ${c(o,"shadow")}${d?h` · ${d}`:u}
          </div>`:u}
    </div>`}};se.properties={hass:{},_config:{state:!0}},se.styles=N`
    .wrap { padding: 8px 16px 16px; }
    .band {
      position: relative; height: 26px; margin: 8px 0 22px;
      border-radius: 13px; background: var(--divider-color, #e0e0e0);
    }
    .fill {
      position: absolute; top: 0; bottom: 0; border-radius: 13px;
      background: color-mix(in srgb, var(--success-color, #4caf50) 35%, transparent);
    }
    .mark { position: absolute; top: -3px; width: 4px; height: 32px; border-radius: 2px; transform: translateX(-2px); }
    .mark.op { background: var(--primary-color, #2196f3); }
    .mark.sp { background: var(--secondary-text-color, #888); }
    .tick { position: absolute; top: 28px; font-size: 11px; color: var(--secondary-text-color); transform: translateX(-50%); }
    .big { font-size: 40px; font-weight: 600; line-height: 1; }
    .big span { font-size: 18px; color: var(--secondary-text-color); }
    .verdict { color: var(--secondary-text-color); margin-bottom: 8px; }
    .cat { margin-left: 8px; opacity: 0.8; }
    .ctl { display: flex; align-items: center; justify-content: center; gap: 18px; margin: 10px 0 4px; }
    .sp { text-align: center; }
    .sp span { display: block; font-size: 12px; color: var(--secondary-text-color); }
    .sp strong { font-size: 20px; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
    .chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;
      border-radius: 14px; background: var(--secondary-background-color); font-size: 13px; }
    .chip ha-icon { --mdc-icon-size: 16px; }
    .chip em { font-style: normal; color: var(--secondary-text-color); }
    .learn { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
    .bar { flex: 1; height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; }
    .bar i { display: block; height: 100%; background: var(--primary-color); }
    .learn span { font-size: 12px; color: var(--secondary-text-color); }
    .pill { padding: 2px 8px; border-radius: 10px; font-size: 11px;
      background: var(--primary-color); color: var(--text-primary-color, #fff); }
    .chart { width: 100%; height: 80px; margin: 10px 0 2px; display: block; }
    .cband { fill: color-mix(in srgb, var(--success-color, #4caf50) 16%, transparent); }
    .cop { fill: none; stroke: var(--primary-color, #2196f3); stroke-width: 2; vector-effect: non-scaling-stroke; }
    .csp { fill: none; stroke: var(--secondary-text-color, #888); stroke-width: 1.5; stroke-dasharray: 3 3; vector-effect: non-scaling-stroke; }
    .chips { cursor: pointer; }
    .monitor { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 2px; }
    .lamp { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
      border-radius: 14px; background: var(--secondary-background-color); font-size: 13px; }
    .lamp .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
    .lamp .lk { color: var(--secondary-text-color); }
    .lamp .lv { font-weight: 600; }
    .lamp .lv small { font-weight: 400; color: var(--secondary-text-color); margin-left: 1px; }
    .dialwrap { position: relative; width: 100%; max-width: 230px; margin: 6px auto 2px; }
    .dial:focus, .ctrclick:focus, .chips:focus { outline: none; }
    .dial:focus-visible, .ctrclick:focus-visible, .chips:focus-visible {
      outline: 2px solid var(--primary-color, #2196f3);
      outline-offset: 2px; border-radius: 10px;
    }
    .dial { width: 100%; display: block; touch-action: none; cursor: pointer; }
    .track { fill: none; stroke: var(--divider-color, #444); stroke-width: 10; stroke-linecap: round; }
    .bandarc { fill: none; stroke: color-mix(in srgb, var(--success-color, #4caf50) 55%, transparent); stroke-width: 10; stroke-linecap: round; }
    .opdot { fill: var(--primary-text-color, #fff); }
    .handle { fill: var(--primary-color, #2196f3); stroke: var(--card-background-color, #1c1c1c); stroke-width: 2; }
    .dialctr { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none; }
    .ctrclick { pointer-events: auto; cursor: pointer; display: flex; flex-direction: column; align-items: center; }
    .handle.heat { fill: var(--state-climate-heat-color, #ff8100); }
    .handle.cool { fill: var(--state-climate-cool-color, #2b9af9); }
    .wrap.compact .dialwrap { max-width: 150px; }
    .dialctr .op { font-size: 38px; font-weight: 600; line-height: 1; }
    .dialctr .op span { font-size: 16px; color: var(--secondary-text-color); }
    .dialctr .opair { font-size: 11px; color: var(--secondary-text-color); margin-top: 2px; }
    .dialctr .soll { font-size: 13px; color: var(--secondary-text-color); margin-top: 4px; }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
    .mould { stroke: var(--warning-color, #ff9800); stroke-width: 3; stroke-linecap: round; }
    .mlbl { fill: var(--warning-color, #ff9800); font-size: 11px; font-weight: 600;
      text-anchor: middle; dominant-baseline: middle; }
    .dial.ro { cursor: default; }
    .presets { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 2px; }
    .preset { display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px;
      border: 1px solid var(--divider-color, #e0e0e0); border-radius: 16px;
      background: var(--card-background-color, transparent);
      color: var(--primary-text-color); font: inherit; font-size: 13px; cursor: pointer; }
    .preset ha-icon { --mdc-icon-size: 16px; }
    .preset.on { background: var(--primary-color, #2196f3);
      color: var(--text-primary-color, #fff); border-color: var(--primary-color, #2196f3); }
    .preset:focus-visible { outline: 2px solid var(--primary-color, #2196f3); outline-offset: 2px; }
    .preset em { font-style: normal; color: var(--secondary-text-color); margin-left: 2px; }
    .preset.on em { color: inherit; opacity: 0.85; }
    .hold { display: flex; align-items: center; gap: 6px; margin: 8px 0 2px; }
    .hold-chip { flex: 1 1 auto; }
    .resume { flex: none; display: inline-flex; align-items: center; justify-content: center;
      width: 28px; height: 28px; padding: 0; border: none; border-radius: 50%;
      background: var(--secondary-background-color); color: var(--secondary-text-color); cursor: pointer; }
    .resume ha-icon { --mdc-icon-size: 18px; }
    .resume:focus-visible { outline: 2px solid var(--primary-color, #2196f3); outline-offset: 2px; }
    .valid { font-size: 11px; color: var(--secondary-text-color); margin-top: 3px; }
    .wrap.compact { padding: 6px 12px 12px; }
    .wrap.compact .dialctr .op { font-size: 30px; }
    .wrap.compact .presets, .wrap.compact .monitor, .wrap.compact .chips { gap: 4px; }
    `;export{se as PoiseCard};
